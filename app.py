# app.py
import logging
import os
import re
import shutil
from io import BytesIO
import uuid
import pandas as pd
from PIL import Image
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from flask import send_from_directory
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# File upload configurations
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
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
    ext = os.path.splitext(filename)[1].lower()
    return ext[1:] in allowed_extensions  # Убираем точку перед проверкой

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


def make_safe_id(field_name):
    # Удаляем все, кроме букв, цифр и подчеркиваний
    return re.sub(r'\W|^(?=\d)', '_', field_name)


def register_fonts():
    fonts = [
        'Manrope-ExtraLight', 'Manrope-Light', 'Manrope-Regular',
        'Manrope-Medium', 'Manrope-SemiBold', 'Manrope-Bold', 'Manrope-ExtraBold'
    ]

    # Путь к папке с шрифтами
    fonts_path = os.path.join(app.root_path, 'static', 'fonts')

    # Регистрируем каждый шрифт
    for font in fonts:
        font_file = f"{font}.ttf"
        font_path = os.path.join(fonts_path, font_file)
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font, font_path))
                logging.info(f"Registered font: {font} from {font_path}")
            except Exception as e:
                logging.error(f"Failed to register font {font}: {e}")
        else:
            logging.warning(f"Font file not found: {font_path}")


# Вызываем функцию регистрации шрифтов при запуске приложения
register_fonts()


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
            # Получаем оригинальное имя файла
            original_filename = template.filename
            logging.debug(f"Original template filename: {original_filename}")

            # Применяем secure_filename
            filename = secure_filename(original_filename)
            logging.debug(f"Secure filename: {filename}")

            # Получаем расширение файла
            ext = os.path.splitext(filename)[1]
            if not ext:
                # Если расширение отсутствует, используем расширение из оригинального имени
                ext = os.path.splitext(original_filename)[1]
                if not ext:
                    # Если в оригинальном имени тоже нет расширения, используем '.png' по умолчанию
                    ext = '.png'
                filename += ext

            # Если после secure_filename имя файла пустое или начинается с точки
            if not filename or filename.startswith('.'):
                # Генерируем уникальное имя файла
                filename = f"template_{uuid.uuid4().hex}{ext}"

            template_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            template.save(template_path)
            session['template_filename'] = filename
            logging.info(f'Template image uploaded successfully as {filename}.')
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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

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

        # Обработка загруженных шрифтов пользователем
        uploaded_font = request.files.get('uploaded_font')
        if uploaded_font and allowed_file(uploaded_font.filename, ALLOWED_FONT_EXTENSIONS):
            font_filename = secure_filename(uploaded_font.filename)
            font_path = os.path.join(app.config['UPLOAD_FOLDER'], font_filename)
            uploaded_font.save(font_path)
            font_name = os.path.splitext(font_filename)[0]
            fonts = [font_name]  # Only the uploaded font is available
            register_fonts([font_filename])  # Можно вызвать для регистрации загруженного шрифта
            # Обновляем конфигурацию шрифтов для полей
            for field in font_configs:
                font_configs[field]['font_name'] = font_name

        session['font_configs'] = font_configs
        return redirect(url_for('position_fields'))
    return render_template('configure_fonts.html', fields=session['selected_columns'], fonts=fonts)

@app.route('/position_fields', methods=['GET', 'POST'])
def position_fields():
    if 'font_configs' not in session:
        return redirect(url_for('configure_fonts'))
    if request.method == 'POST':
        positions = {}
        for field in session['selected_columns']:
            safe_field = make_safe_id(field)
            x_value = request.form.get(f'pos_x_{safe_field}', '0')
            y_value = request.form.get(f'pos_y_{safe_field}', '0')
            max_width_value = request.form.get(f'max_width_{safe_field}', '200')
            logging.debug(f'Получены данные для поля {field}: x={x_value}, y={y_value}, max_width={max_width_value}')
            try:
                x = float(x_value)
                y = float(y_value)
                max_width = float(max_width_value)
            except ValueError as e:
                logging.error(f'Ошибка преобразования данных для поля {field}: {e}')
                flash(f'Некорректные данные для поля {field}. Пожалуйста, введите числовые значения.')
                return redirect(request.url)
            positions[field] = {'x': x, 'y': y, 'max_width': max_width}
        session['positions'] = positions
        logging.info('Позиции полей успешно сохранены.')
        return redirect(url_for('generate_certificates'))
    # Генерируем список полей с безопасными идентификаторами
    fields = [{'name': field, 'id': make_safe_id(field)} for field in session['selected_columns']]
    return render_template('position_fields.html', fields=fields, template_filename=session['template_filename'])


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

    # Открываем изображение, чтобы получить его размеры
    with Image.open(template_path) as img:
        img_width, img_height = img.size

    logging.info(f"Шаблон загружен с размерами: ширина {img_width}px, высота {img_height}px")

    # Генерируем сертификаты
    for index, row in df.iterrows():
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(img_width, img_height))

        # Рисуем фоновое изображение
        c.drawImage(template_path, 0, 0, width=img_width, height=img_height)

        # Рисуем текстовые поля
        for field in fields:
            value = str(row[field]) if pd.notna(row[field]) else ''
            font_name = font_configs[field]['font_name']
            font_size = font_configs[field]['font_size']
            color = font_configs[field]['color']
            x = positions[field]['x']
            y = positions[field]['y']
            max_width = positions[field]['max_width']

            if not value:
                logging.warning(f"Пустое значение для поля '{field}' в строке {index}. Пропуск.")
                continue

            # Проверяем, зарегистрирован ли шрифт
            try:
                c.setFont(font_name, font_size)
                logging.debug(f"Шрифт '{font_name}' успешно применен для поля '{field}' в строке {index}")
            except KeyError:
                logging.error(f"Шрифт '{font_name}' не зарегистрирован. Используется стандартный шрифт.")
                c.setFont("Helvetica", font_size)

            c.setFillColor(HexColor(color))
            text_object = c.beginText()
            text_object.setTextOrigin(x, y)

            # Обработка переноса текста
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

        # Сохраняем PDF
        participant_name = str(row[fields[0]]) if pd.notna(row[fields[0]]) else f"unknown_{index}"
        pdf_filename = f"{participant_name}.pdf"
        pdf_path = os.path.join(app.config['CERTIFICATES_FOLDER'], pdf_filename)
        with open(pdf_path, 'wb') as f:
            f.write(pdf)
        logging.info(f"Сертификат для участника '{participant_name}' успешно создан: {pdf_filename}")

    # Создаем ZIP-архив с сертификатами
    shutil.make_archive('certificates', 'zip', app.config['CERTIFICATES_FOLDER'])
    logging.info("Сертификаты успешно сгенерированы и упакованы в архив certificates.zip")

    # Очищаем папку с сертификатами
    shutil.rmtree(app.config['CERTIFICATES_FOLDER'])
    os.makedirs(app.config['CERTIFICATES_FOLDER'])
    flash('Сертификаты успешно сгенерированы!')
    return send_file('certificates.zip', as_attachment=True)

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('Файл слишком большой. Максимальный размер файла - 16 МБ.')
    return redirect(request.url)

if __name__ == '__main__':
    app.run(debug=False)
