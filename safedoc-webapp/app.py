from flask import Flask, render_template, request, redirect, url_for, flash
import pyodbc
import os
import requests
from azure.cognitiveservices.vision.face import FaceClient
from msrest.authentication import CognitiveServicesCredentials
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configurações do Azure
FACE_API_KEY = 'YOUR_FACE_API_KEY'
FACE_API_ENDPOINT = 'YOUR_FACE_API_ENDPOINT'
FACE_CLIENT = FaceClient(FACE_API_ENDPOINT, CognitiveServicesCredentials(FACE_API_KEY))

# Configuração de banco de dados
SERVER = 'sqlserver-safedoc.database.windows.net'
DATABASE = 'SafeDocDb'
USERNAME = 'azureuser'
PASSWORD = 'Admsenac123!'
DRIVER = '{ODBC Driver 17 for SQL Server}'

# Configuração do diretório de uploads
UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Função para verificar se a extensão do arquivo é permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Função para conectar ao banco de dados
def get_db_connection():
    conn = pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};PORT=1433;DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD}')
    return conn

# Página inicial
@app.route('/')
def index():
    return render_template('index.html')

# Página de registro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        photo = request.files['photo']
        document = request.files['document']

        if photo and allowed_file(photo.filename):
            # Salvar imagem localmente
            filename = secure_filename(photo.filename)
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(photo_path)

            # Verificar se há uma pessoa na foto usando o serviço cognitivo
            detected_faces = FACE_CLIENT.face.detect_with_stream(open(photo_path, 'rb'))
            if not detected_faces:
                flash('A foto não contém uma pessoa válida.', 'error')
                return redirect(url_for('register'))

            # Inserir no banco de dados
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Users (Name, Email, PhotoPath) VALUES (?, ?, ?)", (name, email, photo_path))
            conn.commit()
            cursor.close()

            # Enviar os arquivos para as VMs
            # Enviar foto para a VM Windows e documento para a VM Linux
            # (Aqui você pode usar SCP ou outros métodos de transferência de arquivos)

            flash('Usuário registrado com sucesso!', 'success')
            return redirect(url_for('index'))

    return render_template('register.html')

# Página de consulta
@app.route('/query', methods=['GET', 'POST'])
def query():
    if request.method == 'POST':
        name = request.form['name']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE Name LIKE ?", ('%' + name + '%',))
        users = cursor.fetchall()
        cursor.close()
        return render_template('query.html', users=users)
    return render_template('query.html', users=[])

if __name__ == '__main__':
    app.run(debug=True)
