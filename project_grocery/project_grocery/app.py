from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import os
import pickle
import pandas as pd
import random
import string
from sqlalchemy.orm import sessionmaker

app = Flask(__name__)


# Generate a random secret key using os.urandom
app.secret_key = os.urandom(24).hex()

app.config['TEMPLATES_AUTO_RELOAD'] = True

# Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'mysql+pymysql://root:@localhost/grocery'
) 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Load dataset from CSV
csv_filename = "dataset/filtered.csv"  
df = pd.read_csv(csv_filename)

# Load Trained Model
model_filename = "model/svd_grocery_recommendation.pkl"
with open(model_filename, "rb") as file:
    recommendation_model = pickle.load(file)

# User model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(500), nullable=False)

# Products model
class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False, unique=True)

# Define Cart Model
class Cart(db.Model):
    __tablename__ = 'cart'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete="CASCADE"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id = db.Column(db.String(12), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    purchased_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

class TransactionItem(db.Model):
    __tablename__ = 'transaction_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transaction_id = db.Column(db.String(12), db.ForeignKey('transactions.transaction_id', ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete="CASCADE"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

# Index route
@app.route('/')
def index():
    return render_template('index.html')

# Singup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    message = None
    message_type = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if passwords match
        if password != confirm_password:
            message = "Passwords do not match!"
            message_type = "danger"
            return render_template('signup.html', message=message, message_type=message_type)

        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            message = "User with the same username or email already exists."
            message_type = "danger"
            return render_template('signup.html', message=message, message_type=message_type)

        # Hash the password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Add new user to the database
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        message = "Account created successfully! Please log in."
        message_type = "success"
        return render_template('signup.html', message=message, message_type=message_type)

    return render_template('signup.html', message=message, message_type=message_type)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None
    message_type = 'danger'
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            # Store user info in session
            session['user_id'] = user.id
            session['user_email'] = user.email
            session['username'] = user.username
            return redirect(url_for('dashboard'))  # Redirect to dashboard
        else:
            message = "Invalid email or password. Please try again."
    return render_template('login.html', message=message, message_type=message_type)

# Dashboard route
@app.route('/dashboard')
def dashboard():
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Fetch top 10 products
    top_products = Product.query.limit(10).all()

    return render_template('dashboard.html', username=session.get('username'), products=top_products)

# Search Products in Database
@app.route('/search_products', methods=['GET'])
def search_products():
    search_query = request.args.get('query', '').strip()

    if search_query:
        # Fetch products that match the search term
        matched_products = Product.query.filter(Product.name.ilike(f"%{search_query}%")).limit(10).all()
    else:
        # If no search term, return the default top 10 products
        matched_products = Product.query.limit(10).all()

    # Convert products to JSON format
    products_list = [{"id": product.id, "name": product.name} for product in matched_products]

    return jsonify(products_list)

# Product Detail Route with Recommendations
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    # Fetch product details
    product = Product.query.get_or_404(product_id)

    # Ensure user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']  # Get logged-in user's ID

    # Fetch all product names from database
    all_products = [p.name for p in Product.query.all()]

    # Check if the user exists in the dataset
    if user_id in df["Person"].values:
        # Get products the user has already interacted with
        user_rated_items = df[df["Person"] == user_id]["Item"].values

        if len(user_rated_items) == 0:
            recommended_products = Product.query.limit(5).all()
        else:
            # Generate recommendations for items user has not rated
            predicted_ratings = [
                (item, recommendation_model.predict(user_id, item).est)  # Ensure you're using the trained model
                for item in all_products if item not in user_rated_items
            ]

            # Sort by highest predicted ratings and get top 5 recommendations
            top_recommendations = sorted(predicted_ratings, key=lambda x: x[1], reverse=True)[:5]

            # Fetch recommended product details from database
            recommended_products = Product.query.filter(Product.name.in_([item[0] for item in top_recommendations])).all()
    else:
        # **Handle New Users**
        # Recommend **exactly 5 most frequently purchased items**
        recommended_products_query = db.session.query(
            Product.id, Product.name
        ).join(TransactionItem, Product.id == TransactionItem.product_id) \
            .group_by(Product.id, Product.name) \
            .order_by(db.func.count(TransactionItem.product_id).desc()) \
            .limit(5).all()

        # Ensure 5 products are returned
        recommended_products = [Product.query.get(p.id) for p in recommended_products_query]

        # If fewer than 5 products exist in transactions, add more from the general product list
        if len(recommended_products) < 5:
            additional_products = Product.query.filter(Product.id.notin_([p.id for p in recommended_products])) \
                .limit(5 - len(recommended_products)).all()
            recommended_products.extend(additional_products)

    return render_template('product.html', product=product, recommended_products=recommended_products)

# Route to Add Product to Cart
@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    user_id = session['user_id']
    data = request.get_json()
    product_id = data.get("product_id")

    if not product_id:
        return jsonify({"success": False, "message": "Invalid product ID"}), 400

    # Check if the product exists
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"success": False, "message": "Product not found"}), 404

    # Check if the item is already in the cart
    cart_item = Cart.query.filter_by(user_id=user_id, product_id=product_id).first()

    if cart_item:
        # If the product is already in the cart, increase the quantity
        cart_item.quantity += 1
    else:
        # Add new item to the cart
        new_cart_item = Cart(user_id=user_id, product_id=product_id, quantity=1)
        db.session.add(new_cart_item)

    db.session.commit()

    return jsonify({"success": True, "message": "Product added to cart!"})

# Define Cart Route to Display User's Cart
@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Fetch cart items for the logged-in user
    cart_items = db.session.query(
        Cart.id, Cart.quantity, Product.id.label("product_id"), Product.name
    ).join(Product, Cart.product_id == Product.id).filter(Cart.user_id == user_id).all()

    return render_template('view-cart.html', cart_items=cart_items)

# Route to Remove Item from Cart
@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    data = request.get_json()
    cart_id = data.get("cart_id")

    if not cart_id:
        return jsonify({"success": False, "message": "Invalid cart ID"}), 400

    # Find and delete the cart item
    cart_item = Cart.query.filter_by(id=cart_id, user_id=session['user_id']).first()

    if cart_item:
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({"success": True, "message": "Item removed from cart!"})
    else:
        return jsonify({"success": False, "message": "Item not found"}), 404
    
# Function to Generate Unique Transaction ID
def generate_transaction_id():
    while True:
        transaction_id = "txn" + "".join(random.choices(string.ascii_lowercase + string.digits, k=9))
        existing_txn = Transaction.query.filter_by(transaction_id=transaction_id).first()
        if not existing_txn:  # Ensure it's unique
            return transaction_id

# Route to Handle Buying Products
@app.route('/buy_now', methods=['POST'])
def buy_now():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "User not logged in"}), 401

    user_id = session['user_id']

    # Fetch cart items
    cart_items = db.session.query(Cart.product_id, Cart.quantity).filter(Cart.user_id == user_id).all()

    if not cart_items:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    # Generate a unique transaction ID
    transaction_id = generate_transaction_id()

    # Prevent premature autoflush issues
    with db.session.no_autoflush:
        # Store single transaction entry
        new_transaction = Transaction(transaction_id=transaction_id, user_id=user_id)
        db.session.add(new_transaction)

        # Store multiple items under the same transaction
        for item in cart_items:
            new_transaction_item = TransactionItem(
                transaction_id=transaction_id,
                product_id=item.product_id,
                quantity=item.quantity
            )
            db.session.add(new_transaction_item)

        # Clear user's cart after purchase
        Cart.query.filter_by(user_id=user_id).delete()

    db.session.commit()

    return jsonify({"success": True, "message": "Purchase successful!", "transaction_id": transaction_id})

# Route to View Transaction History
@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Fetch user's transactions
    transactions = db.session.query(
        Transaction.transaction_id,
        Transaction.purchased_at
    ).filter(Transaction.user_id == user_id).order_by(Transaction.purchased_at.desc()).all()

    # Fetch transaction items
    transaction_items = db.session.query(
        TransactionItem.transaction_id,
        Product.name,
        TransactionItem.quantity
    ).join(Product, TransactionItem.product_id == Product.id).filter(
        TransactionItem.transaction_id.in_([t.transaction_id for t in transactions])
    ).all()

    # Organizing transactions with items
    transaction_data = {}
    for txn in transactions:
        transaction_data[txn.transaction_id] = {
            "purchased_at": txn.purchased_at,
            "purchased_items": []  # Updated key name to avoid conflicts
        }

    for item in transaction_items:
        transaction_data[item.transaction_id]["purchased_items"].append({
            "name": item.name,
            "quantity": item.quantity
        })

    return render_template('transactions.html', transactions=transaction_data)

# Logout route
@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Run app
    app.run(debug=True)