from sqlite3 import Cursor
from flask import Flask, config, redirect, request, url_for, render_template, session, flash, Response
import razorpay.errors
from otp import genotp
from cmail import send_mail
from stoken import entoken, dctoken
import mysql.connector
import bcrypt
from flask_session import Session
import os
import razorpay
import re
import pdfkit

app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')

app.secret_key = 'codegnan@123'
mydb = mysql.connector.connect(user='root', host='localhost', password='1234', db='ecom')

client=razorpay.Client(auth=("rzp_test_FSOeGXmMmvG5cj","LVGwV75n2bygfag7nsDhOYVc"))

@app.route('/')
def home():
    return render_template('welcome.html')

@app.route('/index')
def index():
    cursor = mydb.cursor(buffered=True)
    cursor.execute('select bin_to_uuid(itemid), itemname, description, quantity, cost, category, imagename from items')
    itemsdata = cursor.fetchall()
    cursor.execute('select distinct category from items')
    categories = [row[0] for row in cursor.fetchall()]
    return render_template('index.html', itemsdata=itemsdata, categories=categories)

@app.route('/admincreate', methods=['GET', 'POST'])
def admincreate():
    if request.method == 'POST':
        username = request.form['username']
        adminemail = request.form['email']
        password = request.form['password']
        address = request.form['address']
        agreed = request.form['agree']
        cursor = mydb.cursor(buffered=True)
        cursor.execute('select count(adminemail) from admindata where adminemail=%s', [adminemail])
        email_count = cursor.fetchone()
        print(email_count)
        if email_count[0] == 0:
            gotp = genotp()  # server generated otp
            admindata = {'username': username, 'email': adminemail, 'password': password, 'address': address, 'agree': agreed, 'gotp': gotp}
            subject = 'OTP for ECOM Admin app'
            body = f'use this otp for ECOM Admin {gotp}'
            send_mail(to=adminemail, subject=subject, body=body)
            flash('OTP has been sent ')
            return redirect(url_for('adminotp', endata=entoken(data=admindata)))
        elif email_count[0] == 1:
            flash(f'{adminemail} already existed')
    return render_template('admincreate.html')

@app.route('/adminotp/<endata>', methods=['GET', 'POST'])
def adminotp(endata):
    try:
        dcdata = dctoken(data=endata)
    except Exception as e:
        print(f'Error in dcode admindata')
        flash('Could not verify your OTP, please try again')
        return redirect(url_for('admincreate'))
    else:
        if request.method == 'POST':
            aotp = request.form['otp']
            if dcdata['gotp'] == aotp:
                salt = bcrypt.gensalt()
                hashed_password = bcrypt.hashpw(dcdata['password'].encode('utf-8'), salt)
                try:
                    cursor = mydb.cursor(buffered=True)
                    cursor.execute('insert into admindata(adminemail,username,password,address,agree) values(%s,%s,%s,%s,%s)', [dcdata['email'], dcdata['username'], hashed_password, dcdata['address'], dcdata['agree']])
                    mydb.commit()
                except Exception as e:
                    print(f'Error: {e}')
                    flash('Could not register admin, please try again')
                    return redirect(url_for('admincreate'))
                else:
                    flash(f'{dcdata["email"]} registered successfully')
                    return redirect(url_for('adminlogin'))
            else:
                flash('otp was wrong')
        return render_template('adminotp.html', endata=endata)

@app.route('/adminlogin', methods=['GET', 'POST'])
def adminlogin():
    if not session.get('admin'):
        if request.method == 'POST':
            aemail = request.form['email']
            password = request.form['password']
            try:
                cursor = mydb.cursor(buffered=True)
                cursor.execute('select count(adminemail) from admindata where adminemail=%s', [aemail])
                email_count = cursor.fetchone()
                if email_count[0] == 1:
                    cursor.execute('select password from admindata where adminemail=%s', [aemail])
                    stored_password = cursor.fetchone()
                    if bcrypt.checkpw(password.encode('utf-8'), stored_password[0]):
                        session['admin'] = aemail
                        return redirect(url_for('adminpanel'))
                    else:
                        flash('Password is incorrect')
                        return redirect(url_for('adminlogin'))
                else:
                    flash('No such email found')
                    return redirect(url_for('adminlogin'))
            except Exception as e:
                print(f'Error during admin login: {e}')
                flash('An error occurred during login. Please try again.')
        return render_template('adminlogin.html')
    else:
        return redirect(url_for('adminpanel'))

@app.route('/adminpanel', methods=['GET', 'POST'])
def adminpanel():
    return render_template('adminpanel.html')

@app.route('/additem', methods=['GET', 'POST'])
def additem():
    if session.get('admin'):
        if request.method == 'POST':
            item_name = request.form['title']
            item_description = request.form['description']
            item_price = request.form['price']
            item_quantity = request.form['quantity']
            item_category = request.form['category']
            item_image = request.files['file']
            filename = genotp() + '.' + item_image.filename.split('.')[-1]
            print("filename:", filename)
            path = os.path.abspath(__file__)
            print(f'path: {path}')
            dirpath = os.path.dirname(path)
            print(f'dirpath: {dirpath}')
            static_path = os.path.join(dirpath, 'static')
            print(f'static_path: {static_path}')
            item_image.save(os.path.join(static_path, filename))
            try:
                cursor = mydb.cursor(buffered=True)
                cursor.execute('insert into items(itemid,itemname,description,quantity,cost,category,imagename,added_by) values(uuid_to_bin(uuid()),%s,%s,%s,%s,%s,%s,%s)', [item_name, item_description, item_quantity, item_price, item_category, filename, session.get('admin')])
                mydb.commit()
            except Exception as e:
                print(f'Error while adding item: {e}')
                flash('Could not add item, please try again')
                return redirect(url_for('additem'))
            else:
                flash(f'Item {item_name} added successfully')
                return redirect(url_for('adminpanel'))
        return render_template('additem.html')
    else:
        flash('You need to login as admin to add items')
        return redirect(url_for('adminlogin'))

@app.route('/viewallitems', methods=['GET', 'POST'])
def viewallitems():
    if session.get('admin'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where added_by=%s', [session.get('admin')])
            itemsdata = cursor.fetchall()
        except Exception as e:
            print(f'Error : {e}')
            flash('Could not fetch items')
            return redirect('adminpanel')
        else:
            return render_template('viewall_items.html', itemsdata=itemsdata)

@app.route('/viewitem', methods=['GET'])
def viewitem():
    if session.get('admin'):
        itemid = request.args.get('itemid')
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where itemid=uuid_to_bin(%s) and added_by=%s', [itemid, session.get('admin')])
            itemsdata = cursor.fetchone()
        except Exception as e:
            print(f'Error: {e}')
            flash('Could not fetch item details')
            return redirect(url_for('viewallitems'))
        else:
            return render_template('view_item.html', itemsdata=itemsdata)
    else:
        flash('You need to login as admin to view items')
        return redirect(url_for('adminlogin'))

@app.route('/updateitem/<itemid>', methods=['GET', 'POST'])
def updateitem(itemid):
    if session.get('admin'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where itemid=uuid_to_bin(%s) and added_by=%s', [itemid, session.get('admin')])
            itemsdata = cursor.fetchone()
        except Exception as e:
            print(f'error:{e}')
            return render_template('viewall_items.html')
        else:
            if request.method == 'POST':
                item_name = request.form['title']
                item_description = request.form['Description']
                item_quantity = request.form['quantity']
                item_price = request.form['price']
                item_category = request.form['category']
                item_image = request.files['file']

                if item_image.filename == '':
                    filename = itemsdata[6]
                else:
                    filename = genotp() + '.' + item_image.filename.split('.')[-1]
                    path = os.path.abspath(__file__)
                    dirpath = os.path.dirname(path)
                    static_path = os.path.join(dirpath, 'static')
                    try :
                        os.remove(os.path.join(static_path, filename))
                    except Exception as remove_e:
                        print(f"Warning: Could not clean up partially saved image {filename}: {remove_e}")
                    item_image.save(os.path.join(static_path, filename))  # save new image

                cursor.execute('update items set itemname=%s,description=%s,quantity=%s,cost=%s,category=%s,imagename=%s where itemid=uuid_to_bin(%s) and added_by=%s',
                               [item_name, item_description, item_quantity, item_price, item_category, filename, itemid, session.get('admin')])
                mydb.commit()
                flash(f'Item {item_name} updated successfully')
                return redirect(url_for('viewitem', itemid=itemid))
            return render_template('update_item.html', itemsdata=itemsdata)
    else:
        flash('Login as admin')
        return redirect(url_for('adminlogin'))
    
@app.route('/deleteitem/<itemid>', methods=['GET'])
def deleteitem(itemid):
    if session.get('admin'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select imagename from items where itemid=uuid_to_bin(%s) and added_by=%s', [itemid, session.get('admin')])
            item_image = cursor.fetchone()
            if item_image:
                path = os.path.abspath(__file__)
                dirpath = os.path.dirname(path)
                static_path = os.path.join(dirpath, 'static')
                try :
                    os.remove(os.path.join(static_path, item_image[0]))
                except Exception as remove_e:
                    print(f"Warning: Could not clean up partially saved image {item_image[0]}: {remove_e}")
                cursor.execute('delete from items where itemid=uuid_to_bin(%s) and added_by=%s', [itemid, session.get('admin')])
                mydb.commit()
                flash(f'Item {itemid} deleted successfully')
                return redirect(url_for('viewallitems'))
        except Exception as e:
            print(f'Error: {e}')
            flash('Could not delete item, please try again')
            return redirect(url_for('viewallitems'))
    else:
        flash('Login as admin')
        return redirect(url_for('adminlogin'))
    
@app.route('/updateprofile', methods=['GET', 'POST'])
def updateprofile():
    if session.get('admin'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select username,address,phonenumber,imagename from admindata where adminemail=%s', [session.get('admin')])
            admindata = cursor.fetchone()
        except Exception as e:
            print(f'Error: {e}')    
            flash('Could not fetch admin data')
            return redirect(url_for('adminpanel'))
        else:
            if request.method == 'POST':
                adminname = request.form['adminname']
                address = request.form['address']
                phonenumber = request.form['ph_no']
                admin_image = request.files['file']

                if admin_image.filename != '':
                    filename = genotp() + '.' + admin_image.filename.split('.')[-1]
                    path = os.path.abspath(__file__)
                    dirpath = os.path.dirname(path)
                    static_path = os.path.join(dirpath, 'static')
                    try :
                        os.remove(os.path.join(static_path, filename))
                    except Exception as remove_e:
                        print(f"Warning: Could not clean up partially saved image {filename}: {remove_e}")
                    admin_image.save(os.path.join(static_path, filename))
                else:
                    filename = admindata[3]

                cursor.execute('update admindata set username=%s, address=%s, phonenumber=%s, imagename=%s where adminemail=%s',
                               [adminname, address, phonenumber, filename, session.get('admin')])
                mydb.commit()
                flash('Profile updated successfully')
                return redirect(url_for('adminpanel'))
            return render_template('adminupdate.html', admindata=admindata)
        
@app.route('/usercreate', methods=['GET', 'POST'])
def usercreate():
    if request.method == 'POST':
        username = request.form['name']
        useremail = request.form['email']
        password = request.form['password']
        address = request.form['address']
        gender = request.form['usergender']
        otp = genotp()
        userdata = {'username': username, 'useremail': useremail, 'password': password, 'address': address, 'gender' : gender, 'gotp': otp}
        subject = 'OTP for ECOM User Signup'
        body = f'Use this OTP for ECOM User Signup: {otp}'
        send_mail(to=useremail, subject=subject, body=body)
        flash('OTP has been sent to your email')
        return redirect(url_for('userotp', endata=entoken(data=userdata)))

    return render_template('usersignup.html')

@app.route('/userotp/<endata>', methods=['GET', 'POST'])
def userotp(endata):
    try:
        dcdata = dctoken(data=endata)
    except Exception as e:
        print(f'Error decoding userdata: {e}')
        flash('Could not verify your OTP, please try again')
        return redirect(url_for('usercreate'))
    else:
        if request.method == 'POST':
            uotp = request.form['otp']
            if dcdata['gotp'] == uotp:
                salt = bcrypt.gensalt()
                hashed_password = bcrypt.hashpw(dcdata['password'].encode('utf-8'), salt)
                try:
                    cursor = mydb.cursor(buffered=True)
                    cursor.execute('insert into userdata(useremail,username,password,address,gender) values(%s,%s,%s,%s,%s)', [dcdata['useremail'], dcdata['username'], hashed_password, dcdata['address'], dcdata['gender']])
                    mydb.commit()
                except Exception as e:
                    print(f'Error: {e}')
                    flash('Could not register user, please try again')
                    return redirect(url_for('usercreate'))
                else:
                    flash(f'{dcdata["useremail"]} registered successfully')
                    return redirect(url_for('userlogin'))
            else:
                flash('OTP was incorrect')
                return render_template('userotp.html', endata=endata)
        return render_template('userotp.html', endata=endata)

@app.route('/userlogin', methods=['GET', 'POST'])
def userlogin():
    if not session.get('user'):
        if request.method == 'POST':
            uemail = request.form['email']
            password = request.form['password']
            try:
                cursor = mydb.cursor(buffered=True)
                cursor.execute('select count(useremail) from userdata where useremail=%s', [uemail])
                email_count = cursor.fetchone()
                if email_count[0] == 1:
                    cursor.execute('select password from userdata where useremail=%s', [uemail])
                    stored_password = cursor.fetchone()
                    if bcrypt.checkpw(password.encode('utf-8'), stored_password[0]):
                        session['user'] = uemail
                        # Always force cart to be a dict
                        if not isinstance(session.get(uemail), dict):
                            session[uemail] = {}
                        flash('Logged in successfully')
                        print(session)
                        return redirect(url_for('index'))
                    else:
                        flash('Password is incorrect')
                        return redirect(url_for('userlogin'))
                else:
                    flash('No such email found')
                    return redirect(url_for('userlogin'))
            except Exception as e:
                print(f'Error during user login: {e}')
                flash('An error occurred during login. Please try again.')
        return render_template('userlogin.html')
    else:
        return redirect(url_for('index'))

@app.route('/category/<ctype>')
def category(ctype):
    try:
        cursor = mydb.cursor(buffered=True)
        cursor.execute('select bin_to_uuid(itemid), itemname, description, quantity, cost, category, imagename from items where category=%s', [ctype])
        itemsdata = cursor.fetchall()
        cursor.close()
    except Exception as e:
        print(e)
        flash('Could not fetch item categories')
        return redirect(url_for('index'))
    else:
        return render_template('dashboard.html', itemsdata=itemsdata)

@app.route('/addtocart/<itemid>')
def addtocart(itemid):
    if session.get('user'):
        user_email = session.get('user')
        # Always force cart to be a dict
        if not isinstance(session.get(user_email), dict):
            session[user_email] = {}
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid), itemname, description, quantity, cost, category, imagename from items where itemid=uuid_to_bin(%s)', [itemid])
            itemsdata = cursor.fetchone()
        except Exception as e:
            print(f'Error adding item to cart: {e}')
            flash('Could not add item to cart, please try again')
            return redirect(url_for('index'))
        else:
            if itemid not in session[user_email]:
                session[user_email][itemid] = [itemsdata[1], itemsdata[2], 1, itemsdata[4], itemsdata[5], itemsdata[6]]
                session.modified = True
                flash(f'{itemsdata[1]} added to the cart')
                return redirect(url_for('index'))
            else:
                session[user_email][itemid][2] += 1
                session.modified = True
                return redirect(url_for('index'))
    else:    
        flash('You need to login to add items to the cart')
        return redirect(url_for('userlogin'))

@app.route('/viewcart')
def viewcart():
    if session.get('user'):
        items=session[session.get('user')]
        if items:
            return render_template('cart.html',items=items)
        else:
            flash('No items in cart')
            return redirect(url_for("index"))
    else:
        flash('Login first')
        return redirect(url_for('userlogin'))

@app.route('/removefromcart/<itemid>')
def removefromcart(itemid):
    if session.get('user'):
        user_email = session.get('user')
        if isinstance(session.get(user_email), dict) and itemid in session[user_email]:
            session[user_email].pop(itemid)
            session.modified = True
            flash('Item removed from cart')
        else:
            flash('Item not found in cart')
        return redirect(url_for('viewcart'))
    else:
        flash('Login first')
        return redirect(url_for('userlogin'))

@app.route('/pay/<itemid>/<dqyt>/<float:price>', methods=['GET', 'POST'])
def pay(itemid, dqyt, price):
    if session.get('user'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where bin_to_uuid(itemid)=%s', [itemid])
            item = cursor.fetchone()
            cursor.close()
        except Exception as e:
            print(e)
            flash('could not fetch details')
            return redirect(url_for('index'))
        else:
            if request.method == 'POST':
                qyt = int(request.form['qyt'])
                price = price * 100
                amount = price * qyt
                print(amount, qyt, price)
                print(f'creating payment for items :{item[1]}, with {amount}')
                order = client.order.create({
                    "amount": amount,
                    "currency": "INR",
                    "payment_capture": "1"
                })
                print(f'order created,{order}')
                return render_template('pay.html', order=order,itemid=itemid, qyt=qyt, amount=amount, name=item[1], price=price)
            return render_template('pay.html', item=item)

@app.route('/success',methods=['GET','POST'])
def success():
    if request.method == 'POST':
        Payment_id=request.form["razorpay_payment_id"]
        order_id=request.form["razorpay_order_id"]
        order_signature=request.form["razorpay_signature"]
        itemid=request.form["itemid"]
        name=request.form["name"]
        itemqty=request.form["qyt"]
        totalamount=request.form["totalamount"]
        params_dict={
            "razorpay_payment_id":Payment_id,
            "razorpay_order_id":order_id,
            "razorpay_signature":order_signature
        }
        try:
            client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError:
            return 'Payment Failed',400
        else:
            cursor=mydb.cursor(buffered=True)
            cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where itemid=uuid_to_bin(%s)', [itemid])
            item=cursor.fetchone()
            new_quantity = int(item[3]) - int(itemqty)
            cursor.execute('update items set quantity=%s where itemid=uuid_to_bin(%s)', [new_quantity, itemid])
            mydb.commit()
            cursor.execute('select * from userdata where useremail=%s', [session.get('user')])
            userdata = cursor.fetchone()
            order_id = genotp()
            cursor.execute('insert into orders(itemname, totalamount, quantity, paymentby, address) values(%s, %s, %s, %s, %s)',[name, totalamount, itemqty, session.get('user'), userdata[3]])
            mydb.commit()
            cursor.close()
            flash(f'Payment successful for {item[1]}')
            return redirect(url_for('myorders'))
        
@app.route('/myorders')
def myorders():
    if session.get('user'):
        try:
            cursor = mydb.cursor(buffered=True)
            cursor.execute('select * from orders where paymentby=%s', [session.get('user')])
            orders = cursor.fetchall()
            cursor.close()
        except Exception as e:
            print(f'Error fetching orders: {e}')
            flash('Could not fetch your orders')
            return redirect(url_for('index'))
        else:
            return render_template('orders.html', orders=orders)
    else:
        flash('You need to login to view your orders')
        return redirect(url_for('userlogin'))
    
@app.route('/addreview/<itemid>',methods=['GET','POST'])
def addreview(itemid):
    if request.method == 'POST':
        review = request.form['review']
        rating = request.form['rate']
        cursor = mydb.cursor(buffered=True)
        cursor.execute('insert into reviews(review,rating,itemid,user) values(%s,%s,uuid_to_bin(%s),%s)', [review, rating, itemid, session.get('user')])
        mydb.commit()
        cursor.close()
        flash('Review added successfully')
    return redirect(url_for('viewitem', itemid=itemid))

@app.route('/searchdata',methods=['GET','POST'])
def searchdata():
    if request.methos == 'POST':
        sdata=request.form['search']
        strg=['a-zA-Z0-9']
        MATCHING_STRG=re.complie(f'^{strg}',re.IGNORECASE)
        if MATCHING_STRG.search(sdata):
            try:
                cursor=mydb.cursor(buffered=True)
                cursor.execute('select bin_to_uuid(itemid),itemname,description,quantity,cost,category,imagename from items where itemname like %s or description like %s or cost like %s or category like %s',['%'+sdata+'%','%'+sdata+'%','%'+sdata+'%','%'+sdata+'%'])
                items=cursor.fetchall()
                cursor.close()
            except Exception as e:
                print(e)
                flash('could not fetch items')
                return redirect(url_for('index'))
            else:
                return render_template('dashboard.html',items=items)
        else:
            flash('invalid search data')
            return redirect(url_for('index'))

@app.route('/invoice/<orderid>')
def invoice(orderid):
    if session.get('user'):
        try:
            cursor=mydb.cursor(buffered=True)
            cursor.execute('select orderid,itemname,totalamount,quantity,orderdate,paymentby from orders where orderid=%s and paymentby=%s', [orderid, session.get('user')])
            orderdata = cursor.fetchone()
            cursor.execute('select useremail,username,address from userdata where useremail=%s', [session.get('user')])
            userdata = cursor.fetchone()
            html=render_template('bill.html', userdata=userdata, orderdata=orderdata)
            pdf = pdfkit.from_string(html, False,configuration=config)
            response = Response(pdf,content_type='application/pdf')
            response.headers['Content-Disposition'] = 'inline; filename=invoice_{orderid}.pdf'
            return response
        except Exception as e:
            print(f'Error fetching invoice: {e}')
            flash('Could not generate invoice')
            return redirect(url_for('myorders'))
    else:
        flash('You need to login to view invoice')
        return redirect(url_for('userlogin'))

@app.route('/userlogout')
def userlogout():
    if session.get('user'):
        session.pop('user', None)
        flash('You have been logged out successfully')
        return redirect(url_for('index'))
    else:
        return redirect(url_for('index'))

@app.route('/adminlogout')
def adminlogout():
    if session.get('admin'):
        session.pop('admin',None)
        flash('You have been logged out successfully')
        return redirect(url_for('index'))
    else:
        return redirect(url_for('index'))

app.run(debug=True, use_reloader=True)
