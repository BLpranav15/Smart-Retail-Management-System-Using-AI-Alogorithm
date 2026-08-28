import pandas as pd
import pymysql
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from flask_bcrypt import Bcrypt

# Database Configuration
DATABASE_URI = "mysql+pymysql://root:@localhost/grocery"  # Update this if needed

# Create SQLAlchemy Engine & Session
engine = create_engine(DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

# Initialize Flask Bcrypt
bcrypt = Bcrypt()

# Define User Model (Mirrors the 'users' Table)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password = Column(String(500), nullable=False)

# Load CSV File
csv_filename = "dataset/filtered.csv"  
df = pd.read_csv(csv_filename)

# Ensure Unique Users from CSV
unique_users = df["Person"].unique()

# Insert Users into the Database
for person_id in unique_users:
    username = f"testuser{person_id}"
    email = f"testuser{person_id}@gmail.com"
    password = "123456"  # Default password

    # Check if User Already Exists
    existing_user = session.query(User).filter_by(username=username).first()

    if not existing_user:
        # Hash the Password
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Create New User
        new_user = User(username=username, email=email, password=hashed_password)
        session.add(new_user)
        print(f"Inserted: {username} | {email}")

# Commit the Transaction
session.commit()
session.close()
print("All users inserted successfully!")
