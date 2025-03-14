#to pass on values to the html files
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort

#importing the class from the analysis file
from analysis.sales_trend import SalesAnalysis

from forms import SaleForm, SalesEntryForm

#some functions used in the application but don't have impact on the app itself
from main import load_data, get_latest_date, get_amount_rows, percentage  # Import functions from main.py

#imports the csv module 
import csv 

#pandas for analysis 
import pandas as pd 

#securing the filenames when uploading files
from werkzeug.utils import secure_filename

#passwords and confidential data
from dotenv import load_dotenv

# interacting with the operating system to do tasks like file management, environment variables, and system operations
import os

# functools: Provides higher-order functions like wraps, which is used to modify or enhance functions.
from functools import wraps

# jinja2: A templating engine for Python that allows you to generate HTML, XML, or other markup formats.
from jinja2 import Environment

# datetime: Supplies classes for manipulating dates and times.
from datetime import timedelta


#encrypts passwords 
import bcrypt

#secures the app 
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)

# CSRFProtect is used to add Cross-Site Request Forgery (CSRF) protection to the application.
# It ensures that any form submission or state-changing request includes a valid CSRF token,
# preventing malicious websites from performing actions on behalf of the authenticated user without their consent.
#csrf = CSRFProtect(app)

# Set session to be permanent and set a timeout
app.permanent_session_lifetime = timedelta(minutes=30)  # Session expires after 30 minutes
app.config['SESSION_COOKIE_SECURE'] = True  # Ensures that the cookie is only sent over HTTPS

# Add `sum` to the Jinja2 environment
app.jinja_env.globals.update(sum=sum)

# Load environment variables from secure.env
load_dotenv('.env')

# Read credentials from environment variables
app.secret_key = os.getenv('SECRET_KEY')
ADMIN_USER = os.getenv('ADMIN_USER')
ADMIN_PASS = os.getenv('ADMIN_PASS')
csv_file_path = os.getenv('CSV_FILE_PATH')

users = {
    ADMIN_USER: bcrypt.hashpw(ADMIN_PASS.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
}

UPLOAD_FOLDER = 'uploads'  # Directory to save uploaded files
ALLOWED_EXTENSIONS = {'csv'}  # Restrict file types to CSV

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route('/reveal/<section>', methods=['POST'])
def reveal_section(section):
    revealed = request.json.get('revealed', False)
    session[f'{section}_revealed'] = revealed
    return jsonify(success=True)
        
# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    """Check if the file has an allowed extension and isn't empty."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS and filename != ""


def admin_mode_required(f):
    """Decorator to ensure the user is in admin mode."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_mode', False):
            # Abort with a 403 Forbidden if the user is not in admin mode
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/upload_csv', methods=['POST'])
@admin_mode_required
def upload_csv():
    """Handle CSV file upload and process it."""
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']

    if file.filename == '':
        return "No selected file", 400

    if file and allowed_file(file.filename):
        # Save the uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Load the CSV into a DataFrame and process it
        try:
            data = pd.read_csv(filepath)

            # Perform operations with the loaded data
            # For example: Save it to a database or render it on the page
            session['uploaded_file'] = filepath  # Save filepath in the session for further use
            return redirect(url_for('database'))
        except Exception as e:
            return f"Error processing file: {e}", 500
    else:
        return "Invalid file type. Only CSV files are allowed.", 400
    

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Handle login to enable admin tools."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password').encode('utf-8')  # Encode password to bytes for bcrypt

        # Check if the username is 'admin' and proceed with validation
        if username == 'admin':
            # Compare the entered password with the stored hashed password
            if bcrypt.checkpw(password, users.get(username).encode('utf-8')):
                # Grant admin mode access upon successful login
                session['admin_mode'] = True
                session['username'] = username
                session['logged_in'] = True  # Mark as logged in
                return redirect(url_for('home'))  # Redirect to the home page
            else:
                flash("Invalid username or password", "error")
                return redirect(url_for('admin'))  # Redirect back to login page
        else:
            flash("Only the 'admin' user can access the admin tools", "error")
            return redirect(url_for('admin'))  # Redirect back to login page

    return render_template('admin.html')

@app.route('/access_admin')
def access_admin():
    session.clear()  # Clear session or authentication
    session['admin_mode'] = True  # Enable admin mode
    session['uploaded_file'] = "data/sales.csv"
    flash("You are now in Admin Mode.", "success")
    return redirect(url_for('home'))  # Redirect to home

@app.route('/access_mod')
def access_mod():
    session.clear()  # Clear session or authentication
    session['mod_mode'] = True  # Enable mod mode
    session['uploaded_file'] = "data/sales.csv"
    flash("You are now in Mod Mode.", "success")
    return redirect(url_for('home'))  # Redirect to home


@app.route('/exit_mode')
def exit_mod():
    session.pop('mod_mode', None)  # Completely remove mod mode from session
    session.modified = True  # Ensure session updates
    flash("Mode disabled.", "info")
    return redirect(request.referrer or url_for('home'))  # Reload previous page or home

@app.route('/exit_admin')
def exit_admin():
    session.pop('admin_mode', None)  # Completely remove admin mode from session
    session.modified = True  # Ensure session updates
    flash("Admin mode disabled.", "info")
    return redirect(request.referrer or url_for('home'))  # Reload previous page or home


@app.route('/database')
def database():
    """Render the database page with the uploaded or default CSV file."""
    
    # Check if user is an admin (session variable `admin_mode` should be set to True)
    if session.get('admin_mode', False):
        filepath = "data/sales.csv"  # Real data file
    else:
        filepath = "data/dummy_sales.csv"  # Dummy data file for non-admin users
    
    # Check if the file exists
    if not os.path.exists(filepath):
        flash("Data file not found.", "error")
        return redirect(url_for('home'))
    
    # Get the latest date of sale
    latest_date = get_latest_date(filepath)
    rows = get_amount_rows(filepath)
    
    # Load data
    try:
        data = pd.read_csv(filepath)
        data = data.drop(columns=["Timestamp"])
        data_html = data.to_html(classes='data', index=False)
        return render_template('sarasbeads/database.html', latest_date=latest_date, rows=rows, data_table=data_html)
    except Exception as e:
        return f"Error loading data: {e}", 500

CSV_COLUMNS = [
    "Day of the Sale", "Quantity", "Month of the Year", "Day of the Week",
    "Price", "Card amount paid", "Cash amount paid", "Product type",
    "Handmade / Beaded collections", "Sterling Silver collections", "Gold Plated collections",
    "details", "Zirconia Color", "Mohave type", "Birth Stone type",
    "How many items in the set", "Set type"
]

CSV_FILE = 'dummy_sales.csv'

# Ensure the CSV file exists with headers
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

def get_field(form, field, index, default=""):
    """Safely get a field from the submitted form."""
    values = form.getlist(field)
    return values[index] if len(values) > index else default

@app.route('/forms', methods=['GET', 'POST'])
def forms():
    if request.method == 'POST':
        # Ensure the number of sales is provided and valid.
        num_sales_str = request.form.get('num_sales')
        if not num_sales_str or not num_sales_str.isdigit():
            return "Error: Number of sales is missing or invalid.", 400
        num_sales = int(num_sales_str)
        
        sales = []
        for i in range(num_sales):
            # Retrieve all expected fields from the form.
            # Retrieve fields from the form
            day_of_sale    = get_field(request.form, 'day_of_sale', i)
            quantity       = get_field(request.form, 'quantity', i)
            month          = get_field(request.form, 'month', i)
            day_of_week    = get_field(request.form, 'day_of_week', i)
            price          = get_field(request.form, 'price', i)
            card_amount    = get_field(request.form, 'card_amount', i)
            cash_amount    = get_field(request.form, 'cash_amount', i)
            product_type   = get_field(request.form, 'product_type', i)
            category       = get_field(request.form, 'category', i)
            extra_detail   = get_field(request.form, 'extra_detail', i)
            other_detail   = get_field(request.form, 'other_detail', i)
            zirconia      = get_field(request.form, 'zirconia_detail', i)
            mohave        = get_field(request.form, 'mohave_detail', i)
            raw_stone     = get_field(request.form, 'raw_stone_detail', i)
            set_type       = get_field(request.form, 'set_type', i)

            # Determine the collection based on product type.
            # For example, assume that "category" holds a collection value.
            handmade_collection = category if product_type == "Handmade / Beaded" else ""
            sterling_collection = category if product_type == "Sterling Silver" else ""
            gold_collection     = category if product_type == "Gold Plated" else ""

            # Determine details and the stone color column based on extra_detail.
            if extra_detail == "mohave":
                details        = "Mohave"
                mohave_color   = mohave       # The stone color chosen for Mohave
                zirconia_color = ""
                raw_stone_color= ""
            elif extra_detail == "zirconia":
                details        = "Zirconia"
                zirconia_color = zirconia     # The stone color chosen for Zirconia
                mohave_color   = ""
                raw_stone_color= ""
            elif extra_detail == "raw_stone":
                details        = "Raw Stone"
                raw_stone_color= raw_stone    # The stone color chosen for Raw Stone
                mohave_color   = ""
                zirconia_color = ""
            elif extra_detail == "other":
                details        = other_detail   # Use the text provided by the user
                mohave_color   = ""
                zirconia_color = ""
                raw_stone_color= ""
            else:
                details        = extra_detail
                mohave_color   = ""
                zirconia_color = ""
                raw_stone_color= ""

            # Build the sale record using the CSV structure.
            sale = {
                "Day of the Sale": day_of_sale,
                "Quantity": quantity,
                "Month of the Year": month,
                "Day of the Week": day_of_week,
                "Price": price,
                "Card amount paid": card_amount,
                "Cash amount paid": cash_amount,
                "Product type": product_type,
                "Handmade / Beaded collections": handmade_collection,
                "Sterling Silver collections": sterling_collection,
                "Gold Plated collections": gold_collection,
                "details": details,                 # Holds the chosen extra detail or user text.
                "Zirconia Color": zirconia_color,     # Filled if Zirconia was chosen.
                "Mohave type": mohave_color,          # Filled if Mohave was chosen.
                "Birth Stone type": raw_stone_color,  # Filled if Raw Stone was chosen.
                "How many items in the set": "",      # Add logic if available.
                "Set type": set_type
            }

            sales.append(sale)

        # Append the data to the CSV file.
        with open(CSV_FILE, mode='a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
            writer.writerows(sales)

        # After submission, you can show a success page.
        return render_template('submission_success.html', num_sales=num_sales)

    # For GET, render the form (pass any necessary data like product_categories and set_types)
    return render_template('forms.html', product_categories={
                               "Handmade / Beaded": ["Beaded Anklets", "Beaded Bracelets", "Beaded Necklaces", "Earing Charms", "Key Chains", "BookMarks", "SET"],
                               "Sterling Silver": ["Sterling Silver Anklets", "Sterling Silver Bangles", "Sterling Silver Bracelets",
                                                     "Sterling Silver Dangle Earrings", "Sterling Silver Necklaces", "Sterling Silver Nose Rings",
                                                     "Sterling Silver Rings", "Sterling Silver Stud Earrings", "SET"],
                               "Gold Plated": ["Bangles", "Cufflinks", "Bracelets", "Dangling Earrings", "Stud Earrings", "Rings", "Necklaces", "SET"]
                           },
                           set_types=[
                               "Necklace & Studs", "Necklace & Earrings", "Necklace & Ring", "Necklace & Bracelet",
                               "Necklace, Bracelet & Studs", "Necklace, Bracelet & Ring",
                               "Necklace, Bracelet, Ring & Studs", "Bracelet & Studs", "Bracelet & Ring",
                               "Bracelet, Ring & Studs", "Ring & Studs"
                           ])

@app.route('/home')
def home():
    admin_mode = session.get('admin_mode', False)  # Check if admin mode is enabled
    mod_mode = session.get('mod_mode', False)  # Check if mod mode is enabled
    viewer_mode = not (admin_mode or mod_mode)  # Viewer mode is enabled if neither admin nor mod mode is enabled

    if viewer_mode:
        return render_template('sarasbeads/home.html', viewer_mode=True)
    elif admin_mode:
        return render_template('sarasbeads/home.html', admin_mode=True)
    elif mod_mode:
        return render_template('sarasbeads/home.html', mod_mode=True)

@app.route('/')
def index():
    """Render the HUB page as the default landing page."""
    admin_mode = session.get('admin_mode', False)  # Check if admin mode is enabled
    mod_mode = session.get('mod_mode', False)  # Check if mod mode is enabled
    viewer_mode = not (admin_mode or mod_mode)  # Viewer mode is enabled if neither admin nor mod mode is enabled

    if viewer_mode:
        return render_template('hub.html', viewer_mode=True)
    elif admin_mode:
        return render_template('hub.html', admin_mode=True)
    elif mod_mode:
        return render_template('hub.html', mod_mode=True)


# Analysis page - Shows the results of the analysis
@app.route('/analysis', methods=['GET', 'POST'])
def analysis():
    """Render the analysis page with the results of sales analysis."""
    # Load data
    filepath = session.get('uploaded_file', "data/sales.csv")
    if not os.path.exists(filepath):
        flash("Default data file not found.", "error")
        return redirect(url_for('home'))

    try:
        data = pd.read_csv(filepath)
        
        # Ensure 'Day of the sale' is in datetime format
        data['Day of the sale'] = pd.to_datetime(data['Day of the sale'], format='%m/%d/%Y', errors='coerce')
        
        # Handle any invalid dates (if any rows were not converted correctly)
        if data['Day of the sale'].isnull().any():
            flash("Warning: Some 'Day of the sale' entries couldn't be parsed as dates.", "warning")
        
    except Exception as e:
        flash(f"Error reading the data file: {str(e)}", "error")
        return redirect(url_for('home'))

    if data is not None:
        # Initialize the SalesAnalysis class
        analysis = SalesAnalysis(data)

        # Check for filter input
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        product_type_filter = request.form.get('product_type')
        collection_filter = request.form.get('collection')

        filtered_data = data

        # Apply date range filter if dates are provided
        if start_date and end_date:
            try:
                start_date = pd.to_datetime(start_date)
                end_date = pd.to_datetime(end_date)
                filtered_data = analysis.filter_day_range(start_date, end_date)
            except Exception as e:
                flash(f"Invalid date input: {str(e)}", "error")
                return redirect(url_for('analysis'))

        # Generate collection tables using table_collection method
        handmade_table = analysis.table_collection("Handmade / Beaded", filtered_data)
        sterling_silver_table = analysis.table_collection("Sterling Silver", filtered_data)
        gold_plated_table = analysis.table_collection("Gold Plated", filtered_data)

        # Generate the full database table using generate_db method
        full_database_table = analysis.generate_db(filtered_data)

        # Perform other analysis on filtered data
        average_sales = analysis.get_average_sales()
        table_month = analysis.table_month()
        table_week = analysis.table_week()
        table_payment = analysis.table_payment()

        # Render the analysis page with the filtered results and generated tables
        return render_template(
            'sarasbeads/analysis.html',
            month=table_month.to_html(classes='data', header=True, index=True, escape=False),
            week=table_week.to_html(classes='data', header=True, index=True, escape=False),
            payment=table_payment.to_html(classes='data', header=True, index=True, escape=False),
            average_sales=average_sales,

            admin_mode=session.get('admin_mode', False),

            start_date=start_date.strftime('%Y-%m-%d') if start_date else '',
            end_date=end_date.strftime('%Y-%m-%d') if end_date else '',

            product_type_filter=product_type_filter,
            collection_filter=collection_filter,

            handmade_table=handmade_table.to_html(classes='data', header=True, index=True, escape=False),
            sterling_silver_table=sterling_silver_table.to_html(classes='data', header=True, index=True, escape=False),
            gold_plated_table=gold_plated_table.to_html(classes='data', header=True, index=True, escape=False),

            full_database_table=full_database_table.to_html(classes='data', header=True, index=True, escape=False)
        )
    else:
        flash("Error: Could not load the data", "error")
        return redirect(url_for('analysis'))

@app.route('/predictions')
def predictions():
    """Render the predictions page with sales predictions."""
    # Placeholder logic for predictions (you will need to add real prediction code)
    return render_template('sarasbeads/predictions.html')

@app.route('/features')
def features():
    """Render the features page."""
    return render_template('features.html')

@app.route('/getstarted')
def getstarted():
    """Render the get started page."""
    return render_template('getstarted.html')

@app.route('/redirect')
def redirect_page():
    """Render the redirect page."""
    return render_template('redirect.html')

# Main check
if __name__ == '__main__':
    app.run(debug=True)
