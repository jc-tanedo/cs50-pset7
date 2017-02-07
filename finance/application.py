import re
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import gettempdir

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
    uname = rows[0]["username"]
    cash = rows[0]["cash"]

    portfolio = db.execute("SELECT * FROM portfolio WHERE id=:id", id=session["user_id"])
    if portfolio:
        quotes = []
        portfolioValue = 0
        for i, stock in enumerate(portfolio):
            quotes.append(lookup(stock["stock_symbol"]))
            quotes[i]["quantity"] = stock["quantity"]
            quotes[i]["total"] = quotes[i]["price"] * stock["quantity"]
            portfolioValue += quotes[i]["total"]
            quotes[i]["price"] = usd(quotes[i]["price"])
            quotes[i]["total"] = usd(quotes[i]["total"])
        netWorth = portfolioValue + cash
        return render_template("index.html",
                                username=uname, cash=usd(cash), net_worth=usd(netWorth),
                                holdings=quotes, portfolio_value=usd(portfolioValue))
    else:
        return apology("Your portfolio is empty. Please buy some stocks.")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        """Buy shares of stock."""
        stockToBuy = request.form.get("symbol")
        quantity = int(request.form.get("quantity"))
        quoted = lookup(stockToBuy)
        
        if not (stockToBuy and quantity and quoted):
            return apology("Please complete all fields")
        if quantity <= 0:
            return apology("BUYING NEGATIVE / ZERO STOCKS.", "APPROACHING QUANTUM ZONE")
        rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
        cash = rows[0]["cash"]
        if cash < quantity * quoted["price"]:
            return apology("Not enough money in account")
        else:
            cash -= quantity * quoted["price"]
            db.execute("INSERT INTO transactions (id, transaction_type, quantity, price, stock_symbol) VALUES (:id, 'BUY', :quantity, :price, :stock_symbol)",
                        id = session["user_id"], quantity = quantity, price = quoted["price"]*quantity, stock_symbol = stockToBuy)
            db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=cash, id=session["user_id"])
            portfolio = db.execute("SELECT * FROM portfolio WHERE id=:id AND stock_symbol=:symbol", id=session["user_id"], symbol=stockToBuy)
            if portfolio:
                current = portfolio[0]["quantity"]
                db.execute("UPDATE portfolio SET quantity=:qty WHERE id=:id AND stock_symbol=:symbol", qty=current+quantity, id=session["user_id"], symbol=stockToBuy)
            else:
                db.execute("INSERT INTO portfolio (id, stock_symbol, quantity) VALUES (:id, :symbol, :qty)", id=session["user_id"], symbol=stockToBuy, qty=quantity)
            return redirect(url_for("history"))
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
    uname = rows[0]["username"]
    transactions = db.execute("SELECT * FROM transactions WHERE id=:id ORDER BY timestamp DESC", id=session["user_id"])
    if transactions:
        for i in transactions:
            i["price"] = usd(i["price"])
        return render_template("history.html", transactions=transactions, username=uname)
    else:
        return apology("No transactions yet. Go buy or sell some stocks and come back!")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password", "or user not registered")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""
    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/changepassword", methods=["GET", "POST"])
def changepassword():
    if request.method == "POST":
        newPass = request.form.get("npassword")
        veriPass = request.form.get("vpassword")
        oldPass = request.form.get("opassword")
        if not (newPass and veriPass and oldPass):
            return apology("Some fields empty")
        if newPass != veriPass:
            return apology("New passwords do not match")
        rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
        if not pwd_context.verify(oldPass, rows[0]["hash"]):
            return apology("Old password incorrect")
        else:
            db.execute("UPDATE users SET hash=:hash WHERE id=:id", id=session["user_id"], hash=pwd_context.hash(newPass))
        session.clear()
        return redirect(url_for("login"))
    else:
        return render_template("changepassword.html")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        sym = request.form.get("symbol")
        quoted = lookup(sym)
        if quoted:
            quoted["price"] = usd(quoted["price"])
            return render_template("quoted.html", quoted = quoted)
        else:
            return apology("Stock symbol invalid or not found")
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        """Register user."""
        # query database for username if exists
        uname = request.form.get("username")
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=uname)
        if len(rows) == 1:
            return apology("Username already taken!")
        # validity checks
        if request.form.get("password") != request.form.get("vpassword"):
            return apology("Passwords do not match!")
        if re.search(r"[^a-zA-Z0-9]", uname):
            return apology("Invalid characters in username.")
        # register user if no errors
        db.execute("INSERT INTO users (username,hash) VALUES (:username,:hash)",
            username=uname,
            hash=pwd_context.hash(request.form.get("password")))
        return render_template("login.html")
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        """Sell shares of stock."""
        stockToSell = request.form.get("symbol")
        quantity = int(request.form.get("quantity"))
        quoted = lookup(stockToSell)
        if not (stockToSell and quantity and quoted):
            return apology("Please complete all fields")
        if quantity <= 0:
            return apology("EVEN SCHRODINGER'S CAT", "CAN'T SELL THAT AMOUNT OF STOCK")
        rows = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"])
        cash = rows[0]["cash"]
        portfolio = db.execute("SELECT * FROM portfolio WHERE id=:id AND stock_symbol=:symbol", id=session["user_id"], symbol=stockToSell)
        if not portfolio or portfolio[0]["quantity"] < quantity:
            return apology("You don't own enough stock to sell")
        else:
            cash += quantity * quoted["price"]
            db.execute("INSERT INTO transactions (id, transaction_type, quantity, price, stock_symbol) VALUES (:id, 'SELL', :quantity, :price, :stock_symbol)",
                        id = session["user_id"], quantity = quantity, price = quoted["price"]*quantity, stock_symbol = stockToSell)
            db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=cash, id=session["user_id"])
            portfolio = db.execute("SELECT * FROM portfolio WHERE id=:id AND stock_symbol=:symbol", id=session["user_id"], symbol=stockToSell)
            current = portfolio[0]["quantity"]
            db.execute("UPDATE portfolio SET quantity=:qty WHERE id=:id AND stock_symbol=:symbol", qty=current-quantity, id=session["user_id"], symbol=stockToSell)
            return redirect(url_for("history"))
    else:
        return render_template("sell.html")
