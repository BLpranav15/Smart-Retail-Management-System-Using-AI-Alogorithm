import pandas as pd
import pymysql
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# **Database Configuration**
DATABASE_URI = "mysql+pymysql://root:@localhost/grocery"  

# Create SQLAlchemy Engine & Session
engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

# Define Products Table (Mirrors the 'products' Table)
Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(500), nullable=False, unique=True)

# Load CSV File
csv_filename = "dataset/filtered.csv" 
df = pd.read_csv(csv_filename)

# Extract Unique Product Names
unique_products = df["Item"].unique()

# Insert Products into the Database
for product_name in unique_products:
    product_name = product_name.strip()  # Ensure no leading/trailing spaces

    # Check if Product Already Exists
    existing_product = session.query(Product).filter_by(name=product_name).first()

    if not existing_product:
        # Create New Product Entry
        new_product = Product(name=product_name)
        session.add(new_product)
        print(f"Inserted: {product_name}")

# Commit the Transaction
session.commit()
session.close()
print("All products inserted successfully!")
