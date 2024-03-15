#!/usr/bin/python3
import io
import zipfile
from functools import wraps
from io import BytesIO
import base64
from flask import Flask, render_template, redirect, url_for, flash, request, abort, send_file, jsonify, send_from_directory
from flask_bootstrap import Bootstrap
from flask_login import LoginManager, current_user, logout_user, UserMixin, login_user, login_required
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
import os
from flask_paginate import Pagination, get_page_parameter, get_page_args
from wtforms import StringField, SubmitField, PasswordField
from wtforms.validators import DataRequired
from PIL import Image as img
from PIL import ImageDraw
from PIL import ImageFont
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///api_database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
login_manager = LoginManager()
login_manager.init_app(app)
db = SQLAlchemy(app)
Bootstrap(app)
migrate = Migrate(app, db)



def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.id != 1:
            return abort(403)
        return f(*args, **kwargs)

    return decorated_function


@app.template_filter('b64encode')
def b64encode_filter(s):
    return base64.b64encode(s).decode('utf-8')


@app.context_processor
def inject_enumerate():
    return dict(enumerate=enumerate)


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Sign Me Up!")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))


class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.Text)
    data = db.Column(db.LargeBinary)
    category = db.Column(db.Text)
    assigned_to = db.Column(db.String(255))
    results = db.Column(db.String(255))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    x = db.Column(db.Text)
    y = db.Column(db.Text)
    w = db.Column(db.Text)
    h = db.Column(db.Text)


with app.app_context():
    db.create_all()

# Route to save the annotation data


@app.route('/save_annotation', methods=['POST'])
def save_annotation():
  
        annotation_data = request.get_json()
        message = annotation_data["data"]["body"][0]["value"]
        image_data = annotation_data["data"]['target']['source']
        image_cord = annotation_data["data"]['target']['selector']['value']
        id_img = annotation_data["n"]

        # Extract the annotation rectangle coordinates
        x, y, w, h = map(float, image_cord.split(':')[-1].split(','))

        # Decode the base64 image data into bytes
        if image_data.startswith('data:image'):
            _, encoded_data = image_data.split(",", 1)
        image_bytes = base64.b64decode(encoded_data)

        # Load the image from bytes
        image = img.open(io.BytesIO(image_bytes))
        image_width, image_height = image.size

        # Draw a yellow rectangle on the image
        draw = ImageDraw.Draw(image)
        pixel_coordinates = [int(float(x)), int(float(y)), int(
            float(x) + float(w)), int(float(y) + float(h))]
        draw.rectangle(pixel_coordinates, outline="yellow", width=3)

        # Define the text to be written
        text = message
        # Define the font and size for the text
        font_path="arial.ttf"  # Change this path based on your system's fonts
        font_size = 20
        font = ImageFont.truetype(font_path, font_size)

        # Calculate the text width and height
        text_width, text_height = draw.textsize(text)
        # Calculate the coordinates to position the text above the rectangle
        text_x = x + (w - text_width) // 2
        text_y = y - text_height - 5
        # Write the text on the image
        draw.text((text_x, text_y), text, fill="yellow", font=font)
        # Create a buffer to save the image as bytes
        image_buffer = io.BytesIO()
        image.save(image_buffer, format='PNG')
        # Save the modified image to the database
        get_image = Image.query.get(id_img)
        get_image.data = image_buffer.getvalue()
        get_image.x = x
        get_image.y = y 
        get_image.w = w
        get_image.h = h
        db.session.commit()
    
        return "ok"

def divide_images(images, people_names):
    num_images = len(images)
    num_people = len(people_names)
    images_per_person = num_images // num_people
    remainder = num_images % num_people
    start = 0
    end = 0
    people_images = {}
    for i, name in enumerate(people_names):
        end += images_per_person
        if remainder > 0:
            end += 1
            remainder -= 1
        people_images[name] = images[start:end]
        start = end
    return people_images


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/submit', methods=['POST'])
def submit_form():
    option = request.form.get("option")
    get_image = Image.query.get(option.split(",")[1])
    get_image.results = option.split(",")[0]
    db.session.commit()
    return "success"


@app.route('/get_anno', methods=['GET'])
def get_anno():
    img_id = request.args.get('img_id')

    # Check if the image with the given ID exists
    im = Image.query.get(img_id)
    body = [{"type": "TextualBody", "value": "Type here the correct option"}]
    for item in im.category.split(','):
        body.append({"type": "TextualBody", "purpose": "tagging", "value": item})
        
    if not im:
        return jsonify({"error": "Image not found"}), 404

    annotations = [
        {
            "@context": "http://www.w3.org/ns/anno.jsonld",
            "id": f"#annotation",
            "type": "Annotation",
            "body": body,
            "target": {
                "selector": [
                    {
                        "type": "FragmentSelector",
                        "conformsTo": "http://www.w3.org/TR/media-frags/",
                        "value": "xywh=pixel:273,171,123,94",
                    }
                ]
            },
        }
    ]

    return jsonify(annotations)

@app.route('/dashboard')
def index():
    page, per_page, offset = get_page_args()
    per_page = 10  # Number of items per page

    if current_user.is_authenticated:
        name_images = Image.query.filter(
            Image.assigned_to == current_user.name).all()
        name_images.reverse()
        total_images = len(name_images)
        name_images = name_images[offset: offset + per_page]
    else:
        name_images = []
        total_images = 0

    pagination = Pagination(page=page, total=total_images, per_page=per_page)

    return render_template("dashboard.html", current_user=current_user, images=name_images, pagination=pagination)


@app.route('/download_images', methods=['GET', 'POST'])
def download_images():
    if request.method == "POST":
        image_data = []
        option = request.form.get("option")
        r = Image.query.filter(Image.results == option).all()
        if r:
            for img_file in r:
                image = img_file.data
                image_bytes = io.BytesIO(image)
                pil_image = img.open(image_bytes)
                resized_image = pil_image.resize(
                    (img_file.width, img_file.height))
                resized_image_bytes = io.BytesIO()
                resized_image.save(resized_image_bytes, format='PNG')
                encoded_image = base64.b64encode(
                    resized_image_bytes.getvalue()).decode('utf-8')
                image_data.append({'id': img_file.id, 'image': encoded_image,'filename':img_file.filename})
            in_memory_zip = BytesIO()
            with zipfile.ZipFile(in_memory_zip, mode='w') as archive:
                for img_file in image_data:
                    img_id = img_file['id']
                    img_data = base64.b64decode(img_file['image'])
                    img_filename =img_file['filename']
                    archive.writestr(img_filename, img_data)
            in_memory_zip.seek(0)
            return send_file(in_memory_zip, mimetype='application/zip', as_attachment=True, download_name='images.zip')
        else:
            flash("Category results not found")

    cat_list = Image.query.with_entities(Image.category).all()
    a = [p.split(",") for l in cat_list for p in l]
    new_li = set([z for f in a for z in f])
    return render_template("download.html", current_user=current_user, li=new_li)


@app.route('/add_images', methods=['POST', 'GET'])
@admin_only
def admin_index():
    if request.method == 'POST':
        try:
            files = request.files.getlist('image')
            assigned = request.form["assigned_to"].split(",")
            category = request.form['category']
            r = divide_images(files, assigned)
            for assigned_to, files_ass in r.items():
                if files_ass:
                    for file in files_ass:
                        # Read the image file
                        print(str(file.filename))
                        img_file = img.open(file)
                        width, height = img_file.size

                        # Resize the image to 640x640 if it's bigger
                        if img_file.size[0] > 640 or img_file.size[1] > 640:
                            img_file.thumbnail((640, 640))
                        else:
                            # Create a new image with white background
                            background = img.new(
                                'RGB', (640, 640), (255, 255, 255))
                            img_size = img_file.size

                            # Calculate the center position to paste the smaller image
                            left = (640 - img_size[0]) // 2
                            top = (640 - img_size[1]) // 2
                            right = left + img_size[0]
                            bottom = top + img_size[1]

                            # Paste the smaller image onto the white background
                            background.paste(
                                img_file, (left, top, right, bottom))
                            img_file = background

                        # Save the resized image
                        img_buffer = BytesIO()
                        img_file.save(img_buffer, format='PNG')
                        img_data = img_buffer.getvalue()

                        # Create a new image object and save it to the database
                        image = Image(filename=file.filename,data=img_data, category=category,
                                      assigned_to=str(assigned_to).upper(), width=width, height=height)
                        db.session.add(image)
                        db.session.commit()
        except Exception as e:
            print(e)
            return render_template("add_images.html", current_user=current_user, error=str(e))
    return render_template("add_images.html", current_user=current_user)

# @app.route('/add_images', methods=['POST', 'GET'])
# @admin_only
# def admin_index():
#     if request.method == 'POST':
#         files = request.files.getlist('image')
#         assigned = request.form["assigned_to"].split(",")
#         category = request.form['category']
#         r = divide_images(files, assigned)
#         for assigned_to, files_ass in r.items():
#             if files_ass:
#                 for file in files_ass:
#                     img = file.read()
#                     img_buffer = BytesIO(img)
#                     image = Image(data=img_buffer.getvalue(), category=category, assigned_to=str(assigned_to).upper())
#                     db.session.add(image)
#                     db.session.commit()
#     return render_template("add_images.html", current_user=current_user)


@app.route('/', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if request.method == 'POST' and request.form.get("submit") == "Log in":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        # Email doesn't exist or password incorrect.
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Password incorrect, please try again.')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for("index"))
    return render_template('sign-in.html', form=form, current_user=current_user)


@app.route('/sign_up', methods=["GET", "POST"])
def sign():
    form1 = RegisterForm()
    if request.method == 'POST' and 'name' in request.form:
        if User.query.filter_by(email=request.form.get("email")).first():
            # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('sign'))

        hash_and_salted_password = generate_password_hash(
            request.form.get("password"),
            method='pbkdf2:sha256',
            salt_length=8
        )
        name = str(request.form.get("name")).upper()
        new_user = User(
            email=request.form.get("email"),
            name=name,
            password=hash_and_salted_password,
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("index"))
    return render_template('sign-up.html', form1=form1, current_user=current_user)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/.well-known/pki-validation/6F4C06DB597BFC725C250C62E2079C72.txt', methods=["GET", "POST"])
def ssl():
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static')
    full_path = os.path.join(app.root_path, UPLOAD_FOLDER)
    filename = "6F4C06DB597BFC725C250C62E2079C72.txt"
    return send_from_directory("/var/www/static", filename, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)
