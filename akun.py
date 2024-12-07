from flask import Flask, render_template, request, redirect, url_for, flash, session
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Koneksi MongoDB
client = MongoClient('mongodb+srv://test:sparta@cluster0.yt74g.mongodb.net/')
db = client['percetakan']
admins_collection = db['admins']
admin_data = {
    "name": "Admin",
    "email": "admin@gmail.com",
    "password": generate_password_hash("admin123")  # Ganti "admin123" dengan kata sandi admin
}

admins_collection.insert_one(admin_data)
print("Akun admin berhasil dibuat!")
