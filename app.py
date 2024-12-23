import os
import pyodbc
import paramiko
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'ff91935200508524ead9d3e6220966a3'

# Configuração do banco de dados
SERVER = 'sqlserver-safedoc.database.windows.net'
DATABASE = 'SafeDocDb'
USERNAME = 'azureuser'
PASSWORD = 'Admsenac123!'
DRIVER = '{ODBC Driver 18 for SQL Server}'

# Configuração do diretório de uploads
UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS_IMAGES = {'png', 'jpeg', 'jpg'}
ALLOWED_EXTENSIONS_DOCUMENTS = {'pdf', 'docx', 'txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Garantir que o diretório de uploads exista
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Função para verificar se a extensão do arquivo é permitida
def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Função para conectar ao banco de dados
def get_db_connection():
    conn = pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};PORT=1433;DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD}')
    return conn

# Função para verificar se a tabela 'Users' existe
def check_if_table_exists(cursor, table_name):
    cursor.execute(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", (table_name,))
    result = cursor.fetchone()
    return result[0] > 0

# Função para criar a tabela de usuários
def create_users_table(cursor):
    create_table_query = """
    CREATE TABLE Users (
        ID INT PRIMARY KEY IDENTITY,
        Name NVARCHAR(100),
        Email NVARCHAR(100),
        PhotoPath NVARCHAR(255),
        DocumentPath NVARCHAR(255)
    );
    """
    cursor.execute(create_table_query)

# Função para inserir um usuário no banco de dados
def insert_user(cursor, name, email, photo_path, document_path):
    insert_query = "INSERT INTO Users (Name, Email, PhotoPath, DocumentPath) VALUES (?, ?, ?, ?)"
    cursor.execute(insert_query, (name, email, photo_path, document_path))

# Função para enviar arquivos para a VM via SFTP (usando paramiko)
def send_file_to_vm(vm_ip, vm_user, vm_password, file_path, remote_path):
    try:
        transport = paramiko.Transport((vm_ip, 22))
        transport.connect(username=vm_user, password=vm_password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.put(file_path, remote_path)
        sftp.close()
        transport.close()
        logging.debug(f"Arquivo {file_path} enviado com sucesso para {vm_ip}:{remote_path}")
    except Exception as e:
        logging.error(f"Erro ao enviar arquivo para {vm_ip}: {e}")
        raise  # Levanta a exceção para ser capturada no fluxo principal

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        logging.debug("Iniciando o processo de registro...")

        name = request.form['name']
        email = request.form['email']
        photo = request.files['photo']
        document = request.files['document']

        try:
            logging.debug(f"Nome: {name}, Email: {email}")

            # Verificar se a foto foi enviada e se é válida
            if photo and allowed_file(photo.filename, ALLOWED_EXTENSIONS_IMAGES):
                logging.debug(f"Foto recebida: {photo.filename}")
                filename = secure_filename(photo.filename)
                photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                logging.debug(f"Salvando foto em: {photo_path}")

                # Salva a foto no diretório de uploads
                photo.save(photo_path)
                logging.debug(f"{photo_path} salva com sucesso")

                # Verificar o tamanho do arquivo (máximo 4MB)
                if photo.content_length > 4 * 1024 * 1024:
                    flash('A imagem é muito grande. O tamanho máximo permitido é 4 MB.', 'error')
                    logging.debug(f"Imagem muito grande")
                    return redirect(url_for('register'))

                # Verificar o tipo de conteúdo
                logging.debug(f"Tipo de conteúdo do arquivo: {photo.content_type}")
                logging.debug(f"Tamanho do arquivo: {os.path.getsize(photo_path)} bytes")

                # Verificar se o documento foi enviado e se é válido
                document_path = None
                if document and allowed_file(document.filename, ALLOWED_EXTENSIONS_DOCUMENTS):
                    document_filename = secure_filename(document.filename)
                    document_path = os.path.join(app.config['UPLOAD_FOLDER'], document_filename)
                    document.save(document_path)
                    logging.debug(f"Documento salvo com sucesso em: {document_path}")
                else:
                    flash('Por favor, envie um documento válido (pdf, docx, txt).', 'error')
                    return redirect(url_for('register'))

                # Conectar ao banco de dados
                conn = get_db_connection()
                cursor = conn.cursor()

                # Verificar se a tabela 'Users' existe, se não, criar
                if not check_if_table_exists(cursor, 'Users'):
                    logging.debug("Tabela 'Users' não existe. Criando tabela...")
                    create_users_table(cursor)
                    conn.commit()
                    logging.debug("Tabela 'Users' criada com sucesso!")

                # Inserir o usuário na tabela 'Users'
                insert_user(cursor, name, email, photo_path, document_path)
                conn.commit()
                cursor.close()
                logging.debug("Usuário inserido no banco de dados com sucesso!")

                # Enviar os arquivos para as VMs
                vm_windows_ip = '4.228.62.9'
                vm_linux_ip = '4.228.62.17'
                vm_user = 'azureuser'
                vm_password = 'Admsenac123!'

                # Caminho remoto para a foto na VM Windows (diretório C:\Users\azureuser\Pictures)
                remote_photo_path_windows = f'C:/Users/azureuser/Pictures/{filename}'
                remote_document_path_linux = f'/home/azureuser/documentos/{secure_filename(document.filename)}'

                # Enviar a foto para a VM Windows
                send_file_to_vm(vm_windows_ip, vm_user, vm_password, photo_path, remote_photo_path_windows)

                # Enviar o documento para a VM Linux
                send_file_to_vm(vm_linux_ip, vm_user, vm_password, document_path, remote_document_path_linux)

                flash('Usuário registrado com sucesso e arquivos enviados!', 'success')
                logging.debug("Processo concluído com sucesso!")
                return redirect(url_for('query'))

            else:
                flash('Por favor, envie uma foto válida (png, jpg, jpeg).', 'error')
                return redirect(url_for('register'))

        except Exception as e:
            flash(f"Ocorreu um erro durante o registro: {str(e)}", 'error')
            logging.error(f"Erro durante o registro: {str(e)}")
            return redirect(url_for('register'))

    return render_template('register.html')

# Página inicial
@app.route('/')
def index():
    return render_template('index.html')

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
