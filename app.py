from flask import Flask, render_template, request, redirect, url_for, flash
import pyodbc
import os
import requests
from azure.cognitiveservices.vision.face import FaceClient
from msrest.authentication import CognitiveServicesCredentials
from werkzeug.utils import secure_filename
import paramiko

app = Flask(__name__)
app.secret_key = 'ff91935200508524ead9d3e6220966a3'

# Configurações do Azure
FACE_API_KEY = 'FGwaQzEIAtIhWT3U9uvOsPTvMFEUuFQYYWTwEK0vkKbLkXxISZG3JQQJ99AKACZoyfiXJ3w3AAAKACOGpBd6'
FACE_API_ENDPOINT = 'https://safedoc-servicecog.cognitiveservices.azure.com/'
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

# Garantir que o diretório de uploads existe
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Função para verificar se a extensão do arquivo é permitida
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Função para conectar ao banco de dados
def get_db_connection():
    conn = pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};PORT=1433;DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD}')
    return conn

# Função para enviar arquivos para a VM via SFTP (usando paramiko)
def send_file_to_vm(vm_ip, vm_user, vm_password, file_path, remote_path):
    try:
        # Conectar à VM via SSH
        transport = paramiko.Transport((vm_ip, 22))
        transport.connect(username=vm_user, password=vm_password)
        
        # Usar SFTP para enviar o arquivo
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(file_path, remote_path)
        sftp.close()
        transport.close()
        print(f"Arquivo {file_path} enviado com sucesso para {vm_ip}:{remote_path}")
    except Exception as e:
        print(f"Erro ao enviar arquivo para {vm_ip}: {e}")

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
            vm_windows_ip = '4.228.62.9'
            vm_linux_ip = '4.228.62.17'
            vm_user = 'azureuser'
            vm_password = 'Admsenac123!'
            
            # Definir os caminhos remotos onde os arquivos serão armazenados nas VMs
            remote_photo_path_windows = f'/path/on/windows/vm/{filename}'
            remote_document_path_linux = f'/path/on/linux/vm/{document.filename}'

            # Enviar a foto para a VM Windows
            send_file_to_vm(vm_windows_ip, vm_user, vm_password, photo_path, remote_photo_path_windows)
            
            # Salvar o documento localmente
            document_filename = secure_filename(document.filename)
            document_path = os.path.join(app.config['UPLOAD_FOLDER'], document_filename)
            document.save(document_path)
            
            # Enviar o documento para a VM Linux
            send_file_to_vm(vm_linux_ip, vm_user, vm_password, document_path, remote_document_path_linux)

            flash('Usuário registrado com sucesso e arquivos enviados!', 'success')
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
