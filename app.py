from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from datetime import datetime
from PIL import Image
from math import ceil
import paramiko
import pymysql
import os
import io  

app = Flask(__name__, static_url_path="/static")
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')



ALLOWED_EXTENSIONS = {'txt', 'jpg', 'jpeg','png','JPG','JPEG','PNG'}
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024 #8mb
app.config['UPLOAD_FOLDER'] = '/tmp'

def get_db_connection():
    """Create and return a database connection"""
    try:

        conn = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            database=os.getenv('DB_NAME'),
            port=int(os.getenv('DB_PORT', 3306)),  # Default MySQL port
            cursorclass=pymysql.cursors.DictCursor
        )

        print("Successfully connected to database")
        return conn

    except Exception as e:
        print(f"Database connection failed: {str(e)}")
        return None

def checktable():
    """Check if 'uploads' table exists, create if not (MySQL version)"""
    conn = get_db_connection()
    if not conn:
        print("Failed to get database connection")
        return False

    try:
        with conn.cursor() as cursor:
            # Check if table exists
            cursor.execute("""
                SELECT COUNT(*) AS table_exists
                FROM information_schema.tables
                WHERE table_name = 'uploads'
                AND table_schema = DATABASE()
            """)
            result = cursor.fetchone()
            table_exists = result['table_exists'] > 0

            if not table_exists:
                print("Creating uploads table...")
                cursor.execute("""
                    CREATE TABLE uploads (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        size INT NOT NULL,
                        file_type VARCHAR(50),
                        sftp_path VARCHAR(255) NOT NULL,
                        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                print("Table created successfully")
            else:
                print("Table already exists")
        
        return True
        
    except Exception as e:
        print(f"Table check/creation failed: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def connect_sftp():
    """Connect to SFTP server using environment variables"""
    try:
        host = os.getenv('SFTP_HOST')
        username = os.getenv('SFTP_USER')
        password = os.getenv('SFTP_PASS')
        port = int(os.getenv('SFTP_PORT', 22))
        
        # Create SSH client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host,port=port, username=username, password=password)
        
        # Return SFTP client
        return client.open_sftp()
    except Exception as e:
        print(f"SFTP Connection Error: {str(e)}")
        return None

def send_file_sftp(local_path, remote_filename):
    """Send file to SFTP server"""
    sftp = connect_sftp()
    if not sftp:
        return False
    
    try:
        upload_dir = os.getenv('SFTP_UPLOAD_DIR')
        remote_path = f"{upload_dir}/{remote_filename}"
        
        sftp.put(local_path, remote_path)
        return (True, remote_path)
    except Exception as e:
        print(f"SFTP Upload Error: {str(e)}")
        return (False, None)
    finally:
        if sftp:
            sftp.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def hello_world():
    # Initialize default values
    files = []
    current_page = 1
    total_pages = 1
    
    try:
        # Get page number from request
        page = request.args.get('page', 1, type=int)
        per_page = 9  # Items per page

        conn = get_db_connection()
        if conn:
            with conn.cursor() as cursor:
                # Get total count
                cursor.execute("SELECT COUNT(*) AS total FROM uploads")
                result = cursor.fetchone()
                total = result['total'] if result else 0
                
                # Calculate pagination
                total_pages = max(1, ceil(total / per_page))
                current_page = min(max(1, page), total_pages)
                offset = (current_page - 1) * per_page

                # Get paginated files
                cursor.execute("""
                    SELECT filename, file_type, uploaded_at, sftp_path 
                    FROM uploads 
                    ORDER BY uploaded_at DESC 
                    LIMIT %s OFFSET %s
                """, (per_page, offset))
                files = cursor.fetchall()
            
    except Exception as e:
        app.logger.error(f"Database error: {str(e)}")
    finally:
        if conn:
            conn.close()

    return render_template('index.html',
                         files=files,
                         current_page=current_page,
                         total_pages=total_pages)

@app.route('/download/<path:filename>')
def download_file(filename):
    """Download file from SFTP server"""
    sftp = None
    conn = None
    try:
        # First get the SFTP path from database
        conn = get_db_connection()
        if not conn:
            flash('Database connection failed', 'error')
            return redirect(url_for('hello_world'))
            
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT sftp_path FROM uploads 
                WHERE filename = %s
            """, (filename,))
            result = cursor.fetchone()
            
        if not result:
            flash('File record not found', 'error')
            return redirect(url_for('hello_world'))
            
        remote_path = result['sftp_path']
        
        # Connect to SFTP
        sftp = connect_sftp()
        if not sftp:
            flash('SFTP connection failed', 'error')
            return redirect(url_for('hello_world'))
        
        # Create in-memory file buffer
        file_buffer = io.BytesIO()
        sftp.getfo(remote_path, file_buffer)
        file_buffer.seek(0)
        
        return send_file(
            file_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        app.logger.error(f'Download error: {str(e)}')
        flash(f'Download failed: {str(e)}', 'error')
        return redirect(url_for('hello_world'))
    finally:
        if sftp:
            sftp.close()
        if conn:
            conn.close()

@app.route('/upload', methods=['POST'])
def upload_file():

    if not checktable():
        flash('Database configuration error', 'error')
        return redirect(url_for('hello_world'))
    
    if 'file' not in request.files:
        print('No file attached in request')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        print('No file selected')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        print(filename)

        upload_folder = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)  # Create folder if missing
    
        file_path = os.path.join(upload_folder, filename)



    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        file_type = file.mimetype

        # Upload to SFTP
        sftp_success = send_file_sftp(file_path, filename)
        if sftp_success:
            # Get SFTP remote path
            upload_dir = os.getenv('SFTP_UPLOAD_DIR')
            remote_path = f"{upload_dir}/{filename}"

            # Save to database
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO uploads 
                        (filename, size, file_type, sftp_path)
                        VALUES (%s, %s, %s, %s)
                    """, (filename, file_size, file_type, remote_path))
                    conn.commit()
                    flash('File uploaded and record saved successfully!', 'success')
                except Exception as e:
                    conn.rollback()
                    flash(f'Database error: {str(e)}', 'error')
                finally:
                    conn.close()
            else:
                flash('Database connection failed', 'error')
            
            return redirect(url_for('hello_world'))
        
        flash('SFTP upload failed', 'error')
        return redirect(url_for('hello_world'))

    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect('/')
    finally:
        # Clean up file
        if os.path.exists(file_path):
            os.remove(file_path)

if __name__ == "__main__":
    app.run(host="0.0.0.0",debug=True)