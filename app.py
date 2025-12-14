from flask import Flask, render_template, request, redirect, url_for, session
from db.dbhelper import getall, addrecord, getrecord, deleterecord, updaterecord
from datetime import datetime
import sqlite3
import base64
import re
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB file upload limit

def init_db():
    conn = sqlite3.connect('Avila.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idno TEXT NOT NULL,
            name TEXT NOT NULL,
            course_level TEXT NOT NULL,
            time_in TEXT NOT NULL,
            date TEXT NOT NULL,
            UNIQUE(idno, date)  -- Prevents duplicate entries for same student on same day
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idno TEXT UNIQUE NOT NULL,
            lastname TEXT NOT NULL,
            firstname TEXT NOT NULL,
            course TEXT,
            level TEXT,
            avatar TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Create index for faster lookups
    c.execute('CREATE INDEX IF NOT EXISTS idx_attendance_idno_date ON attendance(idno, date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_students_idno ON students(idno)')
    
    conn.commit()
    conn.close()

@app.route("/")
def index():
    return render_template("index.html", show_login=True)

@app.route('/check', methods=['GET'])
def check_student():
    idno = request.args.get('idno')
    print(f"DEBUG: Checking student: {idno}")
    
    student_row = getrecord("students", idno=idno) 
    if student_row:
        student = dict(student_row[0])
        name = student['firstname'] + ' ' + student['lastname']
        course_level = student['course'] + ' ' + student['level']
        import datetime
        now = datetime.datetime.now()
        time_in = now.strftime("%I:%M %p")
        date = now.strftime("%Y-%m-%d")
        
        print(f"DEBUG: Recording attendance for: {name}")
        
        conn = sqlite3.connect('Avila.db')
        c = conn.cursor()
        
        # Check if attendance already exists for this student today
        c.execute("SELECT * FROM attendance WHERE idno = ? AND date = ?", (idno, date))
        existing = c.fetchone()
        
        if existing:
            # Update existing attendance with current time
            print(f"DEBUG: Updating existing attendance for {idno}")
            c.execute("UPDATE attendance SET time_in = ?, name = ?, course_level = ? WHERE idno = ? AND date = ?",
                     (time_in, name, course_level, idno, date))
        else:
            # Insert new attendance record
            print(f"DEBUG: Creating new attendance record for {idno}")
            c.execute("INSERT OR REPLACE INTO attendance (idno, name, course_level, time_in, date) VALUES (?, ?, ?, ?, ?)", 
                     (idno, name, course_level, time_in, date))
        
        conn.commit()
        conn.close()
        
        print(f"DEBUG: Attendance recorded successfully")
        
        html = '''
        <center>
            <img src="''' + url_for('static', filename='images/' + (student['avatar'] if student['avatar'] else 'default_avatar.png')) + '''" 
                 style="width:100px;height:100px;border-radius:50%;object-fit:cover;margin-bottom:10px;">
        </center>
        <table class="w3-table-all">
            <tr><td>IDNO</td><td>''' + student['idno'] + '''</td></tr>
            <tr><td>LASTNAME</td><td>''' + student['lastname'] + '''</td></tr>
            <tr><td>FIRSTNAME</td><td>''' + student['firstname'] + '''</td></tr>
            <tr><td>COURSE</td><td>''' + student['course'] + '''</td></tr>
            <tr><td>LEVEL</td><td>''' + student['level'] + '''</td></tr>
        </table>
        '''
        return html
    else:
        return 'STUDENT NOT FOUND'


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()
        user = getrecord("user", email=email)
        if user:
            if user[0]["password"] == password:
                session['user'] = email
                return redirect(url_for('admin'))
            else:
                error = "Invalid email or password"
                return render_template("login.html", title="Login", error=error)
        else:
            error = "Email not registered. Please register first."
            return render_template("login.html", title="Login", error=error)
    return render_template("login.html", title="Login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if password != confirm_password:
            return "Passwords do not match!"
        if getrecord("user", email=email):
            return "Email already registered."

        addrecord("user", email=email, password=password)
        return redirect(url_for('login'))
    return render_template("register.html", title="Register")

@app.route("/logout")
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()
        edit_id = request.form.get("edit_id")
        if edit_id:
            updaterecord("user", {"email": email, "password": password}, id=edit_id)
        else:
            addrecord("user", email=email, password=password)
        return redirect(url_for('admin'))

    users = getall("user")
    edit_id = request.args.get("edit_id")
    edit_user = getrecord("user", id=edit_id)[0] if edit_id else None
    return render_template("admin.html", users=users, edit_user=edit_user, edit_id=edit_id, title="User Management")

@app.route("/admin/delete/<int:user_id>")
def delete_user(user_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    deleterecord("user", id=user_id)
    return redirect(url_for("admin"))


@app.route("/studentmngt", methods=["GET", "POST"])
def student_mngt():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        idno = request.form["idno"].strip()
        lastname = request.form["lastname"].strip()
        firstname = request.form["firstname"].strip()
        course = request.form["course"].strip()
        level = request.form["level"].strip()
        edit_id = request.form.get("edit_id")
        
        # Store OLD student info before update
        old_student_info = None
        old_idno = None
        if edit_id:
            old_student = getrecord("students", id=edit_id)
            if old_student:
                old_student_info = dict(old_student[0])
                old_idno = old_student_info['idno']
        
        # Handle file upload
        avatar_filename = None
        avatar_file = request.files.get("profile_picture")
        
        images_dir = "static/images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        
        if avatar_file and avatar_file.filename != '':
            allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif'}
            file_ext = os.path.splitext(avatar_file.filename)[1].lower()
            
            if file_ext in allowed_extensions:
                avatar_filename = f"{idno}{file_ext}"
                file_path = os.path.join(images_dir, avatar_filename)
                avatar_file.save(file_path)
            else:
                return f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"

        data = {
            "idno": idno,
            "lastname": lastname,
            "firstname": firstname,
            "course": course,
            "level": level
        }
        
        if edit_id:
            if avatar_filename:
                data["avatar"] = avatar_filename
            else:
                existing_student = getrecord("students", id=edit_id)
                if existing_student and existing_student[0]['avatar']:
                    data["avatar"] = existing_student[0]['avatar']
            
            updaterecord("students", data, id=edit_id)
            
            # Update attendance records if student info changed
            if old_student_info:
                new_name = firstname + ' ' + lastname
                new_course_level = course + ' ' + level
                old_name = old_student_info['firstname'] + ' ' + old_student_info['lastname']
                old_course_level = old_student_info['course'] + ' ' + old_student_info['level']
                
                # Check if anything changed
                if new_name != old_name or new_course_level != old_course_level or idno != old_idno:
                    conn = sqlite3.connect('Avila.db')
                    c = conn.cursor()
                    
                    # Update attendance records with new IDNO if it changed
                    if idno != old_idno:
                        c.execute("UPDATE attendance SET idno = ?, name = ?, course_level = ? WHERE idno = ?",
                                 (idno, new_name, new_course_level, old_idno))
                    else:
                        c.execute("UPDATE attendance SET name = ?, course_level = ? WHERE idno = ?",
                                 (new_name, new_course_level, idno))
                    
                    conn.commit()
                    conn.close()
                    print(f"DEBUG: Updated attendance records for {old_idno} -> {idno}")
                    
        else:
            # Adding new student
            if avatar_filename:
                data["avatar"] = avatar_filename
            else:
                data["avatar"] = "default_avatar.png"
            addrecord("students", **data)

        return redirect(url_for("student_mngt"))

    students_list = getall("students", order_by="lastname ASC, firstname ASC")
    edit_id = request.args.get("edit_id")
    
    edit_student_row = getrecord("students", id=edit_id)
    edit_student = dict(edit_student_row[0]) if edit_id and edit_student_row else None
    
    return render_template("studentmngt.html", students=students_list, edit_student=edit_student)


@app.route("/student/add", methods=["GET", "POST"])
def add_student_page():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == "POST":
        idno = request.form["idno"].strip()
        lastname = request.form["lastname"].strip()
        firstname = request.form["firstname"].strip()
        course = request.form["course"].strip()
        level = request.form["level"].strip()
        avatar_data = request.form.get("avatar")
        avatar_filename = None

        images_dir = "static/images"
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        
        if avatar_data and avatar_data.startswith("data:image/"):
            header, encoded = avatar_data.split(",", 1)
            try:
                avatar_bytes = base64.b64decode(encoded)
                avatar_filename = f"{idno}.png"
                with open(os.path.join(images_dir, avatar_filename), "wb") as f:
                    f.write(avatar_bytes)
            except Exception as e:
                print(f"Error saving avatar: {e}")
                avatar_filename = "default_avatar.png"

        data = {
            "idno": idno,
            "lastname": lastname,
            "firstname": firstname,
            "course": course,
            "level": level,
            "avatar": avatar_filename if avatar_filename else "default_avatar.png"
        }
        
        addrecord("students", **data)
        return redirect(url_for("student_mngt"))

    return render_template("student.html", student=None)

@app.route("/student/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student_page(student_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    student_row = getrecord("students", id=student_id)
    student = dict(student_row[0]) if student_row else None

    if request.method == "POST":
        idno = request.form["idno"].strip()
        lastname = request.form["lastname"].strip()
        firstname = request.form["firstname"].strip()
        course = request.form["course"].strip()
        level = request.form["level"].strip()
        avatar_data = request.form.get("avatar")
        
        # Store old info
        old_idno = student['idno']
        old_name = student['firstname'] + ' ' + student['lastname']
        old_course_level = student['course'] + ' ' + student['level']
        
        data = {
            "idno": idno,
            "lastname": lastname,
            "firstname": firstname,
            "course": course,
            "level": level
        }

        if avatar_data and avatar_data.startswith("data:image/"):
            images_dir = "static/images"
            if not os.path.exists(images_dir):
                os.makedirs(images_dir)
                
            try:
                header, encoded = avatar_data.split(",", 1)
                avatar_bytes = base64.b64decode(encoded)
                avatar_filename = f"{idno}.png"
                with open(os.path.join(images_dir, avatar_filename), "wb") as f:
                    f.write(avatar_bytes)
                data["avatar"] = avatar_filename
            except Exception as e:
                print(f"Error saving avatar: {e}")
                if student and student.get('avatar'):
                    data["avatar"] = student['avatar']

        # Update student record
        updaterecord("students", data, id=student_id)
        
        # Update attendance records if needed
        new_name = firstname + ' ' + lastname
        new_course_level = course + ' ' + level
        
        if new_name != old_name or new_course_level != old_course_level or idno != old_idno:
            conn = sqlite3.connect('Avila.db')
            c = conn.cursor()
            
            # Update attendance records with new IDNO if it changed
            if idno != old_idno:
                c.execute("UPDATE attendance SET idno = ?, name = ?, course_level = ? WHERE idno = ?",
                         (idno, new_name, new_course_level, old_idno))
            else:
                c.execute("UPDATE attendance SET name = ?, course_level = ? WHERE idno = ?",
                         (new_name, new_course_level, idno))
            
            conn.commit()
            conn.close()
            print(f"DEBUG: Updated attendance records for {old_idno} -> {idno}")

        return redirect(url_for("student_mngt"))

    return render_template("student.html", student=student)


@app.route("/student/delete/<int:student_id>")
def delete_student(student_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    # Get student info before deleting
    student_row = getrecord("students", id=student_id)
    if student_row:
        student = dict(student_row[0])
        idno = student['idno']
        
        # Delete attendance records for this student
        conn = sqlite3.connect('Avila.db')
        c = conn.cursor()
        c.execute("DELETE FROM attendance WHERE idno = ?", (idno,))
        conn.commit()
        conn.close()
        print(f"DEBUG: Deleted attendance records for {idno}")
    
    # Delete student
    deleterecord("students", id=student_id)
    return redirect(url_for("student_mngt"))


@app.route("/attend", methods=['GET'])
def attend():
    selected_date = request.args.get('date')
    if not selected_date:
        import datetime
        now = datetime.datetime.now()
        selected_date = now.strftime("%Y-%m-%d")
    
    print(f"DEBUG: Fetching attendance for {selected_date}")

    conn = sqlite3.connect('Avila.db')
    c = conn.cursor()
    
    # Get unique attendance records for the selected date
    c.execute("SELECT DISTINCT idno, name, course_level, time_in FROM attendance WHERE date = ? ORDER BY time_in", (selected_date,))
    records = c.fetchall()
    
    print(f"DEBUG: Found {len(records)} unique records for {selected_date}")
    
    conn.close()
    return render_template('attend.html', records=records, selected_date=selected_date)


@app.route('/attendance', methods=['POST'])
def record_attendance():
    idno = request.form['idno']
    student_row = getrecord("students", idno=idno)
    if student_row:
        student = dict(student_row[0])
        name = student['firstname'] + ' ' + student['lastname']
        course_level = student['course'] + ' ' + student['level']
        import datetime
        now = datetime.datetime.now()
        time_in = now.strftime("%I:%M %p")
        date = now.strftime("%Y-%m-%d")

        conn = sqlite3.connect('Avila.db')
        c = conn.cursor()
        
        # Check if attendance already exists for today
        c.execute("SELECT * FROM attendance WHERE idno = ? AND date = ?", (idno, date))
        existing = c.fetchone()
        
        if existing:
            # Update existing attendance
            c.execute("UPDATE attendance SET time_in = ?, name = ?, course_level = ? WHERE idno = ? AND date = ?", 
                     (time_in, name, course_level, idno, date))
        else:
            # Insert new attendance
            c.execute("INSERT INTO attendance (idno, name, course_level, time_in, date) VALUES (?, ?, ?, ?, ?)", 
                     (idno, name, course_level, time_in, date))
        
        conn.commit()
        conn.close()
        return 'Attendance recorded successfully!'
    else:
        return 'Student not found', 404


# DEBUG ROUTE: Clean duplicate attendance records
@app.route("/clean_duplicates")
def clean_duplicates():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('Avila.db')
    c = conn.cursor()
    
    # Keep only the latest attendance record per student per day
    c.execute('''
        DELETE FROM attendance 
        WHERE id NOT IN (
            SELECT MAX(id) 
            FROM attendance 
            GROUP BY idno, date
        )
    ''')
    
    deleted_count = c.rowcount
    conn.commit()
    conn.close()
    
    return f"Cleaned {deleted_count} duplicate attendance records"


# DEBUG ROUTE: View all attendance
@app.route("/view_all_attendance")
def view_all_attendance():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('Avila.db')
    c = conn.cursor()
    
    # Get all attendance
    c.execute("SELECT * FROM attendance ORDER BY date DESC, time_in DESC")
    all_records = c.fetchall()
    
    # Get all students
    c.execute("SELECT idno, firstname, lastname, course, level FROM students ORDER BY lastname")
    all_students = c.fetchall()
    
    conn.close()
    
    html = "<h1>Attendance Debug View</h1>"
    html += f"<p>Total Attendance Records: {len(all_records)}</p>"
    html += f"<p>Total Students: {len(all_students)}</p>"
    html += '<p><a href="/clean_duplicates">Clean Duplicate Records</a></p>'
    
    html += "<h2>All Attendance Records:</h2>"
    html += "<table border='1'><tr><th>ID</th><th>IDNO</th><th>Name</th><th>Course & Level</th><th>Time In</th><th>Date</th></tr>"
    for record in all_records:
        html += f"<tr><td>{record[0]}</td><td>{record[1]}</td><td>{record[2]}</td><td>{record[3]}</td><td>{record[4]}</td><td>{record[5]}</td></tr>"
    html += "</table>"
    
    html += "<h2>All Students:</h2>"
    html += "<table border='1'><tr><th>IDNO</th><th>First Name</th><th>Last Name</th><th>Course</th><th>Level</th></tr>"
    for student in all_students:
        html += f"<tr><td>{student[0]}</td><td>{student[1]}</td><td>{student[2]}</td><td>{student[3]}</td><td>{student[4]}</td></tr>"
    html += "</table>"
    
    return html


if __name__ == "__main__":
    init_db() 
    app.run(debug=True)