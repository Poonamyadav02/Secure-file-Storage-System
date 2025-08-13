from flask import Flask, render_template, request, redirect, url_for, session, send_file
import os
import mysql.connector
import boto3
import os
from dotenv import load_dotenv
from botocore.exceptions import NoCredentialsError


app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Load environment variables from .env file
load_dotenv()



# AWS Configuration


# S3 Client
s3 = boto3.client('s3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=REGION_NAME
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------- MySQL Configuration ----------
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'file_upload'
}

# ---------- Admin Credentials ----------
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# ---------- Helper function ----------
def validate_login(username, password):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        return user
    except mysql.connector.Error as err:
        print("❌ DB Error:", err)
        return None

# ---------- Routes ----------
@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('upload_page'))
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))

# ---------- User Login ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']
        if uname == ADMIN_USERNAME and pwd == ADMIN_PASSWORD:
            session['admin'] = uname
            return redirect(url_for('admin_dashboard'))
        elif validate_login(uname, pwd):
            session['username'] = uname
            return redirect(url_for('upload_page'))
        else:
            error = "❌ Invalid credentials"
    return render_template('login.html', error=error)

# ---------- User Logout ----------
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('admin', None)
    return redirect(url_for('login'))

# ---------- User Registration ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    message = None
    if request.method == 'POST':
        uname = request.form['username']
        pwd = request.form['password']
        name = request.form['name']
        email = request.form['email']
        try:
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password, name, email) VALUES (%s, %s, %s, %s)", (uname, pwd, name, email))
            conn.commit()
            cursor.close()
            conn.close()
            message = "✅ Registration successful! You can now log in."
        except mysql.connector.errors.IntegrityError:
            message = "❌ Username already exists."
    return render_template("register.html", message=message)

# ---------- File Upload ----------
@app.route('/upload', methods=['GET', 'POST'])
def upload_page():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            return "❌ No file selected", 400

        filename = file.filename

        try:
            # Upload to S3
            s3.upload_fileobj(file, S3_BUCKET, filename)

            # Save metadata to DB
            conn = mysql.connector.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username=%s", (session['username'],))
            user_id = cursor.fetchone()[0]
            s3_url = f"https://{S3_BUCKET}.s3.{REGION_NAME}.amazonaws.com/{filename}"
            cursor.execute("INSERT INTO uploads (user_id, filename, filepath) VALUES (%s, %s, %s)", (user_id, filename, s3_url))
            conn.commit()
            cursor.close()
            conn.close()

            return f"✅ File uploaded successfully to S3!<br>URL: <a href='{s3_url}' target='_blank'>{s3_url}</a>"

        except NoCredentialsError:
            return "❌ AWS credentials not found", 500

    return render_template('index.html')

   

# ---------- Admin Login Page ----------
@app.route('/admin')
def admin_login_redirect():
    return redirect(url_for('login'))

# ---------- Admin Dashboard ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT users.username, users.email, uploads.filename, uploads.upload_time
        FROM users
        LEFT JOIN uploads ON users.id = uploads.user_id
        ORDER BY uploads.upload_time DESC
    """)
    data = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("admin_dashboard.html", data=data)

# ---------- File Download ----------
@app.route('/admin/download/<filename>')
def download_file(filename):
    if 'admin' not in session:
        return redirect(url_for('login'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(filepath, as_attachment=True)

# ---------- Run App ----------
if __name__ == '__main__':
    app.run(debug=True)
