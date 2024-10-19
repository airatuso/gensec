# app.py
import os
import logging
import uuid
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import pandas as pd
from flask import jsonify
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.platypus import Image as RLImage
from io import BytesIO
from PIL import Image
import shutil

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure logging
logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

# File upload configurations
UPLOAD_FOLDER = 'uploads'
CERTIFICATES_FOLDER = 'certificates'
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
ALLOWED_EXCEL_EXTENSIONS = {'xls', 'xlsx'}
ALLOWED_FONT_EXTENSIONS = {'ttf', 'otf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CERTIFICATES_FOLDER'] = CERTIFICATES_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(CERTIFICATES_FOLDER):
    os.makedirs(CERTIFICATES_FOLDER)

# Helper functions
def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def clean_temp_files():
    folder = app.config['UPLOAD_FOLDER']
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
                logging.info(f'Deleted temporary file: {file_path}')
        except Exception as e:
            logging.error(f'Error deleting file {file_path}: {e}')

def register_fonts(font_files):
    for font_file in font_files:
        font_path = os.path.join(app.config['UPLOAD_FOLDER'], font_file)
        font_name = os.path.splitext(font_file)[0]
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        logging.info(f'Registered font: {font_name}')

@app.route('/')
def index():
    clean_temp_files()
    session.clear()
    return render_template('index.html')

@app.route('/upload_template', methods=['GET', 'POST'])
def upload_template():
    if request.method == 'POST':
        template = request.files.get('template')
        if template and allowed_file(template.filename, ALLOWED_IMAGE_EXTENSIONS):
            filename = secure_filename(template.filename)
            template_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            template.save(template_path)
            session['template_filename'] = filename
            logging.info('Template image uploaded successfully.')
            return redirect(url_for('upload_data'))
        else:
            flash('Неверный формат файла. Пожалуйста, загрузите изображение в формате PNG или JPG.')
            return redirect(request.url)
    return render_template('upload_template.html')

@app.route('/upload_data', methods=['GET', 'POST'])
def upload_data():
    if 'template_filename' not in session:
        return redirect(url_for('upload_template'))
    if request.method == 'POST':
        data_file = request.files.get('data_file')
        if data_file and allowed_file(data_file.filename, ALLOWED_EXCEL_EXTENSIONS):
            filename = secure_filename(data_file.filename)
            data_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            data_file.save(data_path)
            session['data_filename'] = filename
            logging.info('Data file uploaded successfully.')
            return redirect(url_for('select_columns'))
        else:
            flash('Неверный формат файла. Пожалуйста, загрузите Excel файл.')
            return redirect(request.url)
    return render_template('upload_data.html')

@app.route('/select_columns', methods=['GET', 'POST'])
def select_columns():
    if 'data_filename' not in session:
        return redirect(url_for('upload_data'))
    data_path = os.path.join(app.config['UPLOAD_FOLDER'], session['data_filename'])
    try:
        df = pd.read_excel(data_path)
        columns = df.columns.tolist()
        logging.info('Columns extracted from Excel file.')
    except Exception as e:
        logging.error(f'Error reading Excel file: {e}')
        flash('Ошибка при чтении Excel файла.')
        return redirect(url_for('upload_data'))
    if request.method == 'POST':
        selected_columns = request.form.getlist('columns')
        if not selected_columns:
            flash('Пожалуйста, выберите хотя бы один столбец.')
            return redirect(request.url)
        session['selected_columns'] = selected_columns
        return redirect(url_for('configure_fonts'))
    return render_template('select_columns.html', columns=columns)

@app.route('/configure_fonts', methods=['GET', 'POST'])
def configure_fonts():
    if 'selected_columns' not in session:
        return redirect(url_for('select_columns'))
    fonts = ['Manrope-ExtraLight', 'Manrope-Light', 'Manrope-Regular', 'Manrope-Medium', 'Manrope-SemiBold', 'Manrope-Bold', 'Manrope-ExtraBold']
    if request.method == 'POST':
        font_configs = {}
        for field in session['selected_columns']:
            font_name = request.form.get(f'font_{field}')
            font_size = int(request.form.get(f'font_size_{field}', 12))
            color = request.form.get(f'color_{field}', '#000000')
            font_configs[field] = {
                'font_name': font_name,
                'font_size': font_size,
                'color': color
            }
        session['font_configs'] = font_configs
        # Handle uploaded fonts
        uploaded_font = request.files.get('uploaded_font')
        if uploaded_font and allowed_file(uploaded_font.filename, ALLOWED_FONT_EXTENSIONS):
            font_filename = secure_filename(uploaded_font.filename)
            font_path = os.path.join(app.config['UPLOAD_FOLDER'], font_filename)
            uploaded_font.save(font_path)
            font_name = os.path.splitext(font_filename)[0]
            fonts = [font_name]  # Only the uploaded font is available
            register_fonts([font_filename])
            # Update font configs to use the uploaded font
            for field in font_configs:
                font_configs[field]['font_name'] = font_name
        else:
            # Register Manrope fonts
            for font in fonts:
                font_file = f'static/fonts/{font}.ttf'
                font_name = font
                pdfmetrics.registerFont(TTFont(font_name, font_file))
        return redirect(url_for('position_fields'))
    return render_template('configure_fonts.html', fields=session['selected_columns'], fonts=fonts)

@app.route('/position_fields', methods=['GET', 'POST'])
def position_fields():
    if 'font_configs' not in session:
        return redirect(url_for('configure_fonts'))
    if request.method == 'POST':
        positions = {}
        for field in session['selected_columns']:
            x = float(request.form.get(f'pos_x_{field}', 0))
            y = float(request.form.get(f'pos_y_{field}', 0))
            max_width = float(request.form.get(f'max_width_{field}', 200))
            positions[field] = {'x': x, 'y': y, 'max_width': max_width}
        session['positions'] = positions
        return redirect(url_for('generate_certificates'))
    return render_template('position_fields.html', fields=session['selected_columns'], template_filename=session['template_filename'])

@app.route('/generate_certificates', methods=['GET'])
def generate_certificates():
    if 'positions' not in session:
        return redirect(url_for('position_fields'))
    data_path = os.path.join(app.config['UPLOAD_FOLDER'], session['data_filename'])
    template_path = os.path.join(app.config['UPLOAD_FOLDER'], session['template_filename'])
    df = pd.read_excel(data_path)
    fields = session['selected_columns']
    font_configs = session['font_configs']
    positions = session['positions']
    # Determine page orientation
    with Image.open(template_path) as img:
        width, height = img.size
    if width > height:
        page_size = landscape(A4)
    else:
        page_size = portrait(A4)
    # Generate certificates
    for index, row in df.iterrows():
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        # Draw background image
        c.drawImage(template_path, 0, 0, width=page_size[0], height=page_size[1])
        # Draw text fields
        for field in fields:
            value = str(row[field])
            font_name = font_configs[field]['font_name']
            font_size = font_configs[field]['font_size']
            color = font_configs[field]['color']
            x = positions[field]['x']
            y = positions[field]['y']
            max_width = positions[field]['max_width']
            c.setFont(font_name, font_size)
            c.setFillColor(HexColor(color))
            text_object = c.beginText()
            text_object.setTextOrigin(x, y)
            # Handle text wrapping
            lines = []
            words = value.split()
            line = ''
            for word in words:
                test_line = line + ' ' + word if line else word
                if pdfmetrics.stringWidth(test_line, font_name, font_size) < max_width:
                    line = test_line
                else:
                    lines.append(line)
                    line = word
            lines.append(line)
            for line in lines:
                text_object.textLine(line)
            c.drawText(text_object)
        c.save()
        pdf = buffer.getvalue()
        buffer.close()
        # Save PDF
        participant_name = row[fields[0]]  # Assuming the first selected field is the name
        pdf_filename = f"{participant_name}.pdf"
        pdf_path = os.path.join(app.config['CERTIFICATES_FOLDER'], pdf_filename)
        with open(pdf_path, 'wb') as f:
            f.write(pdf)
    # Create zip archive
    shutil.make_archive('certificates', 'zip', app.config['CERTIFICATES_FOLDER'])
    # Clear certificates folder
    shutil.rmtree(app.config['CERTIFICATES_FOLDER'])
    os.makedirs(app.config['CERTIFICATES_FOLDER'])
    logging.info('Certificates generated successfully.')
    return send_file('certificates.zip', as_attachment=True)

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('Файл слишком большой. Максимальный размер файла - 16 МБ.')
    return redirect(request.url)

if __name__ == '__main__':
    app.run(debug=True)
