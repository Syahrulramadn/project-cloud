import os
from os.path import join, dirname
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME =  os.environ.get("DB_NAME")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

# Inisialisasi aplikasi Flask
app = Flask(__name__)
app.secret_key = os.urandom(24)
users_collection = db['users']
admins_collection = db['admins']


#FUNGSI VALIDASI LOGIN
def login_required(role=None):
    def wrapper(func):
        @wraps(func)
        def decorated_view(*args, **kwargs):
            if role == 'admin':
                if 'admin' not in session:
                    flash('Harap login sebagai admin terlebih dahulu.', 'warning')
                    return redirect(url_for('admin_login'))
            elif role == 'user':
                if 'user' not in session:
                    flash('Harap login terlebih dahulu.', 'warning')
                    return redirect(url_for('login'))
            return func(*args, **kwargs)
        return decorated_view
    return wrapper
#AKHIR FUNGSI VALIDASI 

@app.context_processor
def inject_user_info():
    # Informasi default jika tidak ada pengguna yang login
    user_info = {
        'logged_in': 'user' in session,
        'user_name': '',
        'user_photo': 'profil_user/default.png'  # Foto default
    }
    
    # Jika pengguna sudah login, ambil informasi dari database
    if 'user' in session:
        user = db.users.find_one({'_id': ObjectId(session['user'])})
        if user:
            user_info['user_name'] = user.get('name', '')
            user_info['user_photo'] = user.get('photo', 'profil_user/default.png')
    
    return user_info

# Fungsi untuk validasi file
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'zip', 'rar'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
def allowed_file_admin(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

#BAGIAN USER
@app.route('/')
def home():
    """Halaman utama."""
    produk_terbaru = list(db.products.find().sort('_id', -1).limit(4))
    return render_template('home.html', active_page='home', produk_terbaru=produk_terbaru)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Fungsi untuk login pengguna."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Cari pengguna berdasarkan email
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            # Login berhasil
            session['userName'] = user['name']
            session['user'] = str(user['_id']) 
            flash('Login berhasil!', 'success')
            return redirect(url_for('home'))
        else:
            # Login gagal
            flash('Email atau kata sandi salah.', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Fungsi untuk registrasi pengguna baru."""
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validasi
        if password != confirm_password:
            flash('Kata sandi dan konfirmasi tidak cocok!', 'danger')
            return redirect(url_for('register'))
        if users_collection.find_one({'email': email}):
            flash('Email sudah terdaftar!', 'danger')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Password minimal 8 karakter!', 'danger')
            return redirect(url_for('register'))

        # Hashing kata sandi dan menyimpan pengguna ke database
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'name': name,
            'phone': phone,
            'email': email,
            'password': hashed_password
        })

        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/produk', methods=['GET'])
def produk():
    products = db.products.find()
    return render_template('produk.html', products=products)

@app.route('/pemesanan/<string:produk_id>', methods=['GET', 'POST'])
@login_required(role='user')
def pemesanan(produk_id):
    produk = db.products.find_one({'_id': ObjectId(produk_id)})
    if not produk:
        flash('Produk tidak ditemukan.', 'danger')
        return redirect(url_for('produk'))

    if request.method == 'POST':
        jumlah = int(request.form['jumlah'])
        ukuran = request.form['ukuran']
        desain = request.files['desain']
        keterangan=request.form['keterangan']
        opsi_pengiriman = request.form['opsi_pengiriman']
        alamat = request.form.get("alamat")  # Ambil alamat pengiriman
        metode_pembayaran = request.form['metode_pembayaran']

        # Cari harga berdasarkan ukuran
        harga_per_satuan = None
        for item in produk.get('dus_harga', []):
            if item['ukuran'] == ukuran:
                harga_per_satuan = int(item['hargaPcs'])
                break

        if harga_per_satuan is None:
            flash('Ukuran tidak valid.', 'danger')
            return redirect(url_for('pemesanan', produk_id=produk_id))

        # Hitung total biaya
        total_biaya = jumlah * harga_per_satuan
        # Validasi file desain
        if desain:
            # Periksa apakah file memiliki nama
            if desain.filename == '':
                flash('Tidak ada file yang dipilih.', 'danger')
                return redirect(url_for('pemesanan', produk_id=produk_id))
            
            # Validasi ekstensi file
            if not allowed_file(desain.filename):
                flash('File desain tidak valid. Gunakan file dengan ekstensi: png, jpg, jpeg, pdf, zip, rar', 'danger')
                return redirect(url_for('pemesanan', produk_id=produk_id))
        # Simpan file desain
        if desain:
            # Generate nama file dengan timestamp untuk menghindari duplikasi nama file
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')  # Format: YYYYMMDDHHMMSS
            nama_file_desain = f"{timestamp}_{secure_filename(desain.filename)}"
            desain_path = os.path.join('./static/uploads/', nama_file_desain)
            desain.save(desain_path)


        # Simpan ke database pemesanan
        order_data = {
            'user_id': ObjectId(session['user']),
            'produk_id': ObjectId(produk_id),
            'nama_produk': produk['nama_produk'], 
            'ukuran': ukuran,
            'harga_per_satuan': harga_per_satuan,
            'jumlah': jumlah,
            'total_biaya': total_biaya,
            'desain': nama_file_desain if desain else None,
            'keterangan':keterangan,
            'opsi_pengiriman': opsi_pengiriman,
            "alamat": alamat if opsi_pengiriman == "Antar ke lokasi" else None,
            'metode_pembayaran': metode_pembayaran,
            'status': 'Konfirmasi',
            "tanggal_pemesanan": datetime.now()  # Menambahkan waktu saat ini
        }

        order = db.orders.insert_one(order_data)
        order_id = str(order.inserted_id) 

        flash(f'Pemesanan berhasil dilakukan, Total biaya: Rp {total_biaya:,}. Mohon unggah bukti pembayaran!', 'success')
        return redirect(url_for('detail_pesanan', order_id=order_id))

    metode_pembayaran = list(db.pembayaran.find())
    return render_template('pemesanan.html', produk=produk, metode_pembayaran=metode_pembayaran)

@app.route('/detail_pesanan/<string:order_id>', methods=['GET'])
@login_required(role='user')
def detail_pesanan(order_id):
    # Ambil data pesanan berdasarkan order_id
    order = db.orders.find_one({'_id': ObjectId(order_id)})

    if not order:
        flash('Pesanan tidak ditemukan.', 'danger')
        return redirect(url_for('home'))

    user = db.users.find_one({'_id': order['user_id']})

    # Ambil informasi produk berdasarkan produk_id yang ada di pesanan
    produk = db.products.find_one({'_id': ObjectId(order['produk_id'])})

    return render_template('detail_pesanan.html', order=order, produk=produk, user=user)

@app.route('/upload_bukti/<string:order_id>', methods=['POST'])
@login_required(role='user')
def upload_bukti(order_id):
    # Ambil data pesanan berdasarkan order_id
    order = db.orders.find_one({'_id': ObjectId(order_id)})

    if not order:
        flash('Pesanan tidak ditemukan.', 'danger')
        return redirect(url_for('home'))

    # Periksa apakah ada file yang diunggah
    if 'bukti_pembayaran' not in request.files:
        flash('File bukti pembayaran tidak ditemukan.', 'danger')
        return redirect(url_for('detail_pesanan', order_id=order_id))

    bukti_pembayaran = request.files['bukti_pembayaran']

    # Validasi file
    if bukti_pembayaran and allowed_file(bukti_pembayaran.filename):
        # Simpan file bukti pembayaran
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')  # Format: YYYYMMDDHHMMSS
        filename = f"{timestamp}_{secure_filename(bukti_pembayaran.filename)}"
        bukti_path = os.path.join('./static/bukti_pembayaran', filename)
        bukti_pembayaran.save(bukti_path)

        # Perbarui pesanan dengan path bukti pembayaran
        db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'bukti_pembayaran': filename, 'status': 'Konfirmasi'}}
        )

        flash('Bukti pembayaran berhasil diunggah.', 'success')
        return redirect(url_for('riwayat_pemesanan', order_id=order_id))
    else:
        flash('File bukti pembayaran tidak valid. Format yang diperbolehkan: png, jpg, jpeg, pdf, zip, rar', 'danger')

    return redirect(url_for('detail_pesanan', order_id=order_id))



@app.route('/riwayat_pemesanan', methods=['GET'])
@login_required(role='user')
def riwayat_pemesanan():
    # Ambil ID pengguna dari sesi
    user_id = ObjectId(session['user'])

    # Ambil semua data pesanan milik pengguna
    orders = list(db.orders.find({'user_id': user_id}).sort('_id', -1))

    return render_template('riwayat_pemesanan.html', orders=orders)

app.config['UPLOAD_FOLDER'] = './static/profil_user/'  # Folder baru untuk menyimpan foto
@app.route('/profil', methods=['GET'])
@login_required(role='user')
def profil():
    user_id = session.get('user')
    user = db.users.find_one({'_id': ObjectId(user_id)})
    if not user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('home'))

    # Tentukan foto default jika tidak ada foto
    photo_filename = user.get('photo', 'profil_user/default.png')  # Foto default berada di folder static/profil_user

    return render_template('profil_user.html', user=user, photo_filename=photo_filename)

@app.route('/update_profile', methods=['GET', 'POST'])
@login_required(role='user')
def update_profile():
    user_id = session.get('user')
    user = db.users.find_one({'_id': ObjectId(user_id)})
    if not user:
        flash('Pengguna tidak ditemukan.', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        jenis_kelamin = request.form['jenis_kelamin']
        tanggal_lahir = request.form['tanggal_lahir']
        photo = request.files.get('photo')
        
        # Gunakan foto lama atau foto default
        photo_filename = user.get('photo', 'profil_user/default.png')

        # Cek apakah file foto diunggah
        if photo and photo.filename != '':
            # Cek apakah format file diizinkan
            if not allowed_file_admin(photo.filename):
                flash('Format file tidak valid. Gunakan file jpg, jpeg, atau png.', 'danger')
                return redirect(url_for('profil'))

            # Buat folder profil_user jika belum ada
            user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
            if not os.path.exists(user_folder):
                os.makedirs(user_folder)

            # Generate nama file dengan datetime untuk menghindari duplikasi nama file
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            file_extension = os.path.splitext(photo.filename)[1]
            filename = f'{timestamp}{file_extension}'
            photo_path = os.path.join(user_folder, filename)
            photo.save(photo_path)
            photo_filename = f'profil_user/{user_id}/{filename}'

        # Update data pengguna di database
        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'jenis_kelamin':jenis_kelamin,
                    'tanggal_lahir': tanggal_lahir,
                    'photo': photo_filename
                }
            }
        )
        flash('Profil berhasil diperbarui!', 'success')
        return redirect(url_for('profil'))


@app.route('/logout')
def logout():
    """Logout pengguna dan hapus sesi."""
    session.clear()
    session.pop('user', None)
    flash('Anda telah keluar.', 'info')
    return redirect(url_for('login'))
#AKHIR BAGIAN USER


#BAGIAN ADMIN
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Login untuk admin."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Cari admin berdasarkan email
        admin = admins_collection.find_one({'email': email})
        if admin and check_password_hash(admin['password'], password):
            # Login berhasil untuk admin
            session['admin'] = admin['name']
            flash('Login admin berhasil!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            # Login gagal
            flash('Email atau kata sandi salah.', 'danger')

    return render_template('admin_login.html')

@app.route('/adminDashboard')
@login_required(role='admin')
def admin_dashboard():
    return render_template('admin_dashboard.html', admin=session['admin'])


@app.route('/totals', methods=['GET'])
@login_required(role='admin')
def get_totals():
    total_customers = db.users.count_documents({})
    total_products = db.products.count_documents({})
    total_orders = db.orders.count_documents({})
    
    return jsonify({
        'total_customers': total_customers,
        'total_products': total_products,
        'total_orders': total_orders
    })

#DATA PELANGGAN
@app.route('/adminPelanggan', methods=['GET'])
@login_required(role='admin')
def adminPelanggan():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    users = db.users.find()
    page = int(request.args.get('page', 1))
    per_page = 5
    total_users = users_collection.count_documents({})
    total_pages = (total_users + per_page - 1) // per_page

    users = list(users_collection.find().skip((page - 1) * per_page).limit(per_page))
    return render_template('adminPelanggan.html', users=users, page=page, total_pages=total_pages, admin=admin)


@app.route('/hapusDataPelanggan/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def hapus_data_pelanggan(_id):
    db.users.delete_one({'_id': ObjectId(_id)})
    flash('Akun pelanggan berhasil dihapus!', 'success')  # Tambahkan flash message
    return redirect(url_for('adminPelanggan'))
#AKHIR DATA PELANGGAN

#DATA PRODUK
@app.route('/adminProduk')
@login_required(role='admin')
def adminProduk():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    products = db.products.find()
    return render_template('adminProduk.html', products=products, admin=admin)


@app.route('/tambahDataProduk', methods=['GET', 'POST'])
@login_required(role='admin')
def tambah_data_produk():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        kategori = request.form['kategori']
        namaProduk = request.form['namaProduk']
        deskripsi = request.form['deskripsi']
        ukuran = request.form.getlist('ukuran[]')
        hargaPcs = request.form.getlist('hargaPcs[]')
        photo = request.files['photo']

        if not kategori or not namaProduk or not deskripsi or not ukuran or not hargaPcs or not photo:
            flash('Semua bidang harus diisi!', 'error')  # Tambahkan flash message
            # return "Semua bidang harus diisi!", 400
        
        # Validasi ekstensi file
        if not allowed_file_admin(photo.filename):
            flash('File gambar tidak valid. Format yang diperbolehkan: png, jpg, jpeg', 'danger')
            return redirect(url_for('tambah_data_produk'))
            # return "Jenis file tidak diizinkan!", 400


        # Membuat nama file gambar dengan timestamp
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")  # Format timestamp
        nama_file_asli = photo.filename
        nama_file_gambar = f"{timestamp}_{secure_filename(nama_file_asli)}"  # Menambahkan timestamp pada nama file gambar
        file_path = f'./static/assets/imgProduk/{nama_file_gambar}'
        photo.save(file_path)

        dus_harga_list = [{'ukuran': u, 'hargaPcs': h} for u, h in zip(ukuran, hargaPcs)]
        doc = {
            'kategori': kategori,
            'nama_produk': namaProduk,
            'deskripsi': deskripsi,
            'dus_harga': dus_harga_list,
            'photo': nama_file_gambar
        }

        db.products.insert_one(doc)
        flash('Produk berhasil ditambahkan!', 'success')  # Tambahkan flash message
        return redirect(url_for("adminProduk"))

    return render_template('tambahDataProduk.html', admin=admin)


@app.route('/editDataProduk/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def edit_data_produk(_id):
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        kategori = request.form['kategori']
        namaProduk = request.form['namaProduk']
        deskripsi = request.form['deskripsi']
        ukuran = request.form.getlist('ukuran[]')
        hargaPcs = request.form.getlist('hargaPcs[]')
        photo = request.files.get('photo')
        
        nama_file_gambar = None
        if photo and photo.filename:
            # Check if the file is allowed (assuming you have an allowed_file function)
            if photo and allowed_file_admin(photo.filename):
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                nama_file_asli = photo.filename
                nama_file_gambar = f"{timestamp}_{secure_filename(nama_file_asli)}"
                file_path = f'./static/assets/imgProduk/{nama_file_gambar}'
                photo.save(file_path)
            else:
                flash('File gambar tidak valid. Format yang diperbolehkan: png, jpg, jpeg!', 'danger')
                return redirect(url_for('edit_data_produk', _id=_id))

        doc = {
            'kategori': kategori,
            'nama_produk': namaProduk,
            'deskripsi': deskripsi,
            'dus_harga': [{'ukuran': u, 'hargaPcs': h} for u, h in zip(ukuran, hargaPcs)]
        }
        if nama_file_gambar:
            doc['photo'] = nama_file_gambar

        db.products.update_one({'_id': ObjectId(_id)}, {'$set': doc})
        flash('Produk berhasil diperbarui!', 'success')  # Tambahkan flash message
        return redirect(url_for('adminProduk'))

    data = db.products.find_one({'_id': ObjectId(_id)})
    return render_template('editDataProduk.html', data=data, admin=admin)


@app.route('/hapusDataProduk/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def hapus_data_produk(_id):
    db.products.delete_one({'_id': ObjectId(_id)})
    flash('Produk berhasil dihapus!', 'success')  # Tambahkan flash message
    return redirect(url_for('adminProduk'))
#AKHIR DATA PRODUK


#DATA PEMBAYARAN
@app.route('/adminPembayaran', methods=['GET'])
@login_required(role='admin')
def adminPembayaran():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    pembayaran = db.pembayaran.find()
    page = int(request.args.get('page', 1))
    per_page = 5
    total_products = db.pembayaran.count_documents({})
    total_pages = (total_products + per_page - 1) // per_page

    pembayaran = list(db.pembayaran.find().skip((page - 1) * per_page).limit(per_page))
    return render_template('adminPembayaran.html', pembayaran=pembayaran, page=page, total_pages=total_pages, admin=admin)


@app.route('/tambahDataPembayaran', methods=['GET', 'POST'])
@login_required(role='admin')
def tambah_data_pembayaran():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        jenisPembayaran = request.form['jenisPembayaran']
        metodePembayaran = request.form['metodePembayaran']
        nomorPembayaran = request.form['nomorPembayaran']

        doc = {
            'jenisPembayaran': jenisPembayaran,
            'metodePembayaran': metodePembayaran,
            'nomorPembayaran': nomorPembayaran
        }

        db.pembayaran.insert_one(doc)
        flash('Data pembayaran berhasil ditambahkan!', 'success')  # Tambahkan flash message
        return redirect(url_for("adminPembayaran"))

    return render_template('tambahDataPembayaran.html', admin=admin)


@app.route('/editDataPembayaran/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def edit_data_pembayaran(_id):
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        jenisPembayaran = request.form['jenisPembayaran']
        metodePembayaran = request.form['metodePembayaran']
        nomorPembayaran = request.form['nomorPembayaran']

        doc = {
            'jenisPembayaran': jenisPembayaran,
            'metodePembayaran': metodePembayaran,
            'nomorPembayaran': nomorPembayaran
        }

        db.pembayaran.update_one({'_id': ObjectId(_id)}, {'$set': doc})
        flash('Data pembayaran berhasil diperbarui!', 'success')  # Tambahkan flash message
        return redirect(url_for('adminPembayaran'))

    data = db.pembayaran.find_one({'_id': ObjectId(_id)})
    return render_template('editDataPembayaran.html', data=data, admin=admin)


@app.route('/hapusDataPembayaran/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def hapus_data_pembayaran(_id):
    db.pembayaran.delete_one({'_id': ObjectId(_id)})
    flash('Data pembayaran berhasil dihapus!', 'success')  # Tambahkan flash message
    return redirect(url_for('adminPembayaran'))
#AKHIR DATA PEMBAYARAN

#DATA RIWAYAT PEMESANAN
@app.route('/adminDaftarPemesanan', methods=['GET'])
@login_required(role='admin')
def adminDaftarPemesanan():
    admin = db.admin.find_one({'_id': ObjectId(session.get('admin_id'))})
    page = int(request.args.get('page', 1))
    per_page = 5
    
    # Definisi status pesanan yang mungkin
    order_statuses = [
        'Konfirmasi', 
        'Diproses', 
        'Dikirim', 
        'Selesai', 
        'Dibatalkan'
    ]
    
    # Hitung total pesanan
    total_orders = db.orders.count_documents({})
    total_pages = (total_orders + per_page - 1) // per_page
    
    # Ambil pesanan dengan pagination
    orders = list(db.orders.find().sort('tanggal_pemesanan', -1).skip((page - 1) * per_page).limit(per_page))
    
    # Tambahkan informasi pengguna untuk setiap pesanan
    for order in orders:
        user = db.users.find_one({'_id': order['user_id']})
        order['user_name'] = user['name'] if user else 'Pengguna Tidak Dikenal'
    
    return render_template(
        'adminDaftarPemesanan.html', 
        orders=orders, 
        page=page, 
        total_pages=total_pages, 
        admin=admin,
        order_statuses=order_statuses
    )

@app.route('/adminDetailPemesanan/<string:order_id>', methods=['GET'])
@login_required(role='admin')
def admin_detail_pemesanan(order_id):
    # Ambil data pesanan berdasarkan order_id
    order = db.orders.find_one({'_id': ObjectId(order_id)})

    if not order:
        flash('Pesanan tidak ditemukan.', 'danger')
        return redirect(url_for('adminDaftarPemesanan'))

    # Ambil informasi pengguna
    user = db.users.find_one({'_id': order['user_id']})
    
    # Ambil informasi produk
    produk = db.products.find_one({'_id': order['produk_id']})

    return render_template('adminDetailPemesanan.html', order=order, user=user, produk=produk)

@app.route('/update_order_status', methods=['POST'])
@login_required(role='admin')
def update_order_status():
    try:
        # Get order ID and new status from form submission
        order_id = request.form.get('order_id')
        new_status = request.form.get('new_status')
        
        # Validasi input
        if not order_id or not new_status:
            flash('Invalid order ID or status', 'error')
            return redirect(url_for('adminDaftarPemesanan'))
        
        # Update order status di database
        result = db.orders.update_one(
            {'_id': ObjectId(order_id)},
            {'$set': {'status': new_status}}
        )
        
        # Cek jika status di perbarui
        if result.modified_count > 0:
            flash('Status pemesanan berhasil diperbarui!', 'success')
        else:
            flash('Tidak ada pesanan yang ditemukan atau status tidak berubah!', 'warning')
        
        return redirect(url_for('adminDaftarPemesanan'))
    
    except Exception as e:
        # Log the error and show a user-friendly message
        app.logger.error(f"Terjadi kesalahan saat memperbarui status pesanan: {str(e)}")
        flash('Terjadi kesalahan saat memperbarui status pesanan', 'error')
        return redirect(url_for('adminDaftarPemesanan'))
    
@app.route('/hapusDataPemesanan_order/<string:order_id>', methods=['POST'])
@login_required(role='admin')
def hapus_data_pemesanan(order_id):
    try:
        # Cek apakah pesanan ada
        order = db.orders.find_one({'_id': ObjectId(order_id)})
        
        if not order:
            flash('Pesanan tidak ditemukan.', 'danger')
            return redirect(url_for('adminDaftarPemesanan'))
        
        # Hapus pesanan dari database
        result = db.orders.delete_one({'_id': ObjectId(order_id)})
        
        # Cek apakah penghapusan berhasil
        if result.deleted_count > 0:
            flash('Pesanan berhasil dihapus!', 'success')
        else:
            flash('Gagal menghapus pesanan.', 'error')
        
        return redirect(url_for('adminDaftarPemesanan'))
    
    except Exception as e:
        # Log error dan tampilkan pesan kesalahan
        app.logger.error(f"Terjadi kesalahan saat menghapus pesanan: {str(e)}")
        flash('Terjadi kesalahan saat menghapus pesanan', 'error')
        return redirect(url_for('adminDaftarPemesanan'))

# route data admin start
@app.route('/adminDataAdmin')
@login_required(role='admin')
def adminDataAdmin():
        admin = db.admins.find_one({'_id': ObjectId(session.get('admin_id'))})
        admin = db.admins.find()
        page = int(request.args.get('page', 1))
        per_page = 5  # Number of products per page
        total_admin = db.admins.count_documents({})
        total_pages = (total_admin + per_page - 1) // per_page

        admin = list(db.admins.find().skip((page - 1) * per_page).limit(per_page))

        return render_template('adminDataAdmin.html', admin=admin, page=page, total_pages=total_pages)

@app.route('/tambahDataAdmin', methods=['GET', 'POST'])
@login_required(role='admin')
def tambah_data_admin():
    admin = db.admins.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validasi
        if password != confirm_password:
            flash('Kata sandi dan konfirmasi tidak cocok.', 'danger')
            return redirect(url_for('tambah_data_admin'))
        if db.admins.find_one({'email': email}):
            flash('Email sudah terdaftar.', 'danger')
            return redirect(url_for('tambah_data_admin'))
        if len(password) < 8:
            flash('password minimal 8 karakter', 'danger')
            return redirect(url_for('tambah_data_admin'))

        hashed_password=generate_password_hash(password)
        doc = {
            "name": name,
            "email": email,
            "password": hashed_password  # Ganti "admin123" dengan kata sandi admin
        }
        
        db.admins.insert_one(doc)
        flash('Akun admin berhasil ditambahkan!', 'success')
        return redirect(url_for("adminDataAdmin"))
        
    return render_template('tambahDataAdmin.html', admin=admin)

@app.route('/editDataAdmin/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def edit_data_admin(_id):
    admin = db.admins.find_one({'_id': ObjectId(session.get('admin_id'))})
    if request.method == 'POST':
        name = request.form['name']
        email=request.form['email']
        password = generate_password_hash(request.form['password'])

        doc = {
            'name': name,
            'email':email,
            'password': password
        }
        
        # Update database
        db.admins.update_one({'_id': ObjectId(_id)}, {'$set': doc})
        flash('Data admin berhasil diperbarui!', 'success')
        return redirect(url_for('adminDataAdmin'))
    
    data = db.admins.find_one({'_id': ObjectId(_id)})
    return render_template('editDataAdmin.html', data=data, admin=admin)

@app.route('/hapusDataAdmin/<string:_id>', methods=["GET", "POST"])
@login_required(role='admin')
def hapus_data_admin(_id):
    db.admins.delete_one({'_id': ObjectId(_id)})
    flash('Akun admin berhasil dihapus!', 'success' )
    return redirect(url_for('adminDataAdmin'))
# route akun admin end

@app.route('/admin/logout')
def admin_logout():
    """Logout admin dan hapus sesi."""
    session.clear()
    session.pop('admin', None)
    flash('Anda telah keluar sebagai admin.', 'info')
    return redirect(url_for('admin_login'))

#AKHIR BAGIAN ADMIN

if __name__ == '__main__':
    app.run('0.0.0.0', port=5000, debug=True)

