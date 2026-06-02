import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId
from functools import wraps

utcnow = lambda: datetime.now(timezone.utc).replace(tzinfo=None)

app = Flask(__name__)
app.secret_key = "iampujitha"

app.config["MONGO_URI"] = "mongodb+srv://241fa04b85:pujitha@cluster0.jme75pf.mongodb.net/?appName=Cluster0"
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

mongo = PyMongo(app)

db = mongo.db

if db is None:
    db = mongo.cx["social_productivity"]

USERS_COL = "users"
CHALLENGES_COL = "challenges"
PROGRESS_COL = "progress"
JOINS_COL = "joins"

CHALLENGE_CATEGORIES = ["Study", "Fitness", "Reading", "Coding", "Writing", "Meditation", "Art", "Music", "Other"]

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_by_username(username):
    return mongo.cx["social_productivity"][USERS_COL].find_one({"username": username})

def get_user_by_email(email):
    return mongo.cx["social_productivity"][USERS_COL].find_one({"email": email})

def get_user_by_id(user_id):
    return mongo.cx["social_productivity"][USERS_COL].find_one({"_id": ObjectId(user_id)})

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first!", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required!", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return render_template("register.html")

        if len(password) < 4:
            flash("Password must be at least 4 characters!", "danger")
            return render_template("register.html")

        if get_user_by_username(username):
            flash("Username already exists!", "danger")
            return render_template("register.html")

        if get_user_by_email(email):
            flash("Email already registered!", "danger")
            return render_template("register.html")

        hashed_pw = generate_password_hash(password)
        user = {
            "username": username,
            "email": email,
            "password": hashed_pw,
            "created_at": utcnow(),
            "total_points": 0,
            "challenges_completed": 0
        }
        mongo.cx["social_productivity"][USERS_COL].insert_one(user)
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("All fields are required!", "danger")
            return render_template("login.html")

        user = get_user_by_username(username)
        if not user or not check_password_hash(user["password"], password):
            flash("Invalid username or password!", "danger")
            return render_template("login.html")

        session["user_id"] = str(user["_id"])
        session["username"] = user["username"]
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    user = get_user_by_id(user_id)

    my_challenges = list(mongo.cx["social_productivity"][CHALLENGES_COL].find({"created_by": user_id}).sort("created_at", -1))

    joined_challenge_ids = [j["challenge_id"] for j in mongo.cx["social_productivity"][JOINS_COL].find({"user_id": user_id})]
    joined_challenges = list(mongo.cx["social_productivity"][CHALLENGES_COL].find({"_id": {"$in": [ObjectId(cid) for cid in joined_challenge_ids]}}))

    all_challenge_ids = set()
    for c in my_challenges:
        all_challenge_ids.add(str(c["_id"]))
    for c in joined_challenges:
        all_challenge_ids.add(str(c["_id"]))

    today = utcnow().strftime("%Y-%m-%d")
    progress_data = {}
    for cid in all_challenge_ids:
        entry = mongo.cx["social_productivity"][PROGRESS_COL].find_one({
            "user_id": user_id,
            "challenge_id": cid,
            "date": today
        })
        progress_data[cid] = entry["completed"] if entry else False

    open_challenges = list(mongo.cx["social_productivity"][CHALLENGES_COL].find({
        "is_active": True,
        "created_by": {"$ne": user_id},
        "_id": {"$nin": [ObjectId(cid) for cid in joined_challenge_ids]}
    }).sort("created_at", -1))

    return render_template("dashboard.html",
                         user=user,
                         my_challenges=my_challenges,
                         joined_challenges=joined_challenges,
                         progress_data=progress_data,
                         open_challenges=open_challenges,
                         categories=CHALLENGE_CATEGORIES,
                         now=utcnow)

@app.route("/challenge/create", methods=["GET", "POST"])
@login_required
def create_challenge():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "Other")
        duration_days = request.form.get("duration_days", 7, type=int)

        if not title:
            flash("Challenge title is required!", "danger")
            return render_template("create_challenge.html", categories=CHALLENGE_CATEGORIES)

        if duration_days < 1 or duration_days > 365:
            flash("Duration must be between 1 and 365 days!", "danger")
            return render_template("create_challenge.html", categories=CHALLENGE_CATEGORIES)

        challenge = {
            "title": title,
            "description": description,
            "category": category,
            "duration_days": duration_days,
            "created_by": session["user_id"],
            "creator_name": session["username"],
            "created_at": utcnow(),
            "end_date": utcnow() + timedelta(days=duration_days),
            "is_active": True,
            "participants_count": 0
        }
        result = mongo.cx["social_productivity"][CHALLENGES_COL].insert_one(challenge)

        mongo.cx["social_productivity"][JOINS_COL].insert_one({
            "user_id": session["user_id"],
            "challenge_id": str(result.inserted_id),
            "joined_at": utcnow()
        })
        mongo.cx["social_productivity"][CHALLENGES_COL].update_one(
            {"_id": result.inserted_id},
            {"$inc": {"participants_count": 1}}
        )

        flash("Challenge created successfully!", "success")
        return redirect(url_for("challenge_detail", challenge_id=str(result.inserted_id)))

    return render_template("create_challenge.html", categories=CHALLENGE_CATEGORIES)

@app.route("/challenge/<challenge_id>")
@login_required
def challenge_detail(challenge_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    is_participant = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id
    }) is not None

    participants = []
    participant_entries = list(mongo.cx["social_productivity"][JOINS_COL].find({"challenge_id": challenge_id}))
    for entry in participant_entries:
        user_data = get_user_by_id(entry["user_id"])
        if user_data:
            participants.append({
                "user_id": entry["user_id"],
                "username": user_data["username"],
                "joined_at": entry["joined_at"]
            })

    leaderboard_data = []
    today = utcnow().strftime("%Y-%m-%d")
    for p in participants:
        total_done = mongo.cx["social_productivity"][PROGRESS_COL].count_documents({
            "user_id": p["user_id"],
            "challenge_id": challenge_id,
            "completed": True
        })
        total_hours = 0
        hours_pipeline = list(mongo.cx["social_productivity"][PROGRESS_COL].aggregate([
            {"$match": {"user_id": p["user_id"], "challenge_id": challenge_id, "completed": True}},
            {"$group": {"_id": None, "total": {"$sum": "$hours"}}}
        ]))
        if hours_pipeline:
            total_hours = hours_pipeline[0].get("total", 0) or 0
        streak = calculate_streak(p["user_id"], challenge_id)
        today_done = mongo.cx["social_productivity"][PROGRESS_COL].find_one({
            "user_id": p["user_id"],
            "challenge_id": challenge_id,
            "date": today,
            "completed": True
        }) is not None
        leaderboard_data.append({
            "user_id": p["user_id"],
            "username": p["username"],
            "total_done": total_done,
            "total_hours": total_hours,
            "streak": streak,
            "today_done": today_done
        })

    leaderboard_data.sort(key=lambda x: (-x["total_hours"], -x["streak"]))

    user_today_entry = mongo.cx["social_productivity"][PROGRESS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id,
        "date": today,
        "completed": True
    })
    user_today_done = user_today_entry is not None
    user_today_proof = user_today_entry.get("proof", "") if user_today_entry else ""
    user_today_hours = user_today_entry.get("hours", 0) if user_today_entry else 0

    participant_ids = [p["user_id"] for p in participants]
    invite_candidates = list(mongo.cx["social_productivity"][USERS_COL].find({
        "_id": {"$nin": [ObjectId(uid) for uid in participant_ids]}
    }))

    all_proofs = {}
    all_images = {}
    today_progress = list(mongo.cx["social_productivity"][PROGRESS_COL].find({
        "challenge_id": challenge_id,
        "date": today,
        "completed": True,
        "image_filename": {"$exists": True, "$ne": ""}
    }))
    for tp in today_progress:
        all_proofs[tp["user_id"]] = tp.get("proof", "")
        all_images[tp["user_id"]] = tp.get("image_filename", "")

    return render_template("challenge_detail.html",
                         challenge=challenge,
                         participants=participants,
                         is_participant=is_participant,
                         is_owner=(challenge.get("created_by") == session["user_id"]),
                         leaderboard=leaderboard_data,
                         user_today_done=user_today_done,
                         user_today_proof=user_today_proof,
                         user_today_hours=user_today_hours,
                         user_today_image=user_today_entry.get("image_filename", "") if user_today_entry else "",
                         all_proofs=all_proofs,
                         all_images=all_images,
                         invite_candidates=invite_candidates)

@app.route("/challenge/<challenge_id>/delete")
@login_required
def delete_challenge(challenge_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    if challenge.get("created_by") != session["user_id"]:
        flash("Only the creator can delete this challenge!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    mongo.cx["social_productivity"][JOINS_COL].delete_many({"challenge_id": challenge_id})
    mongo.cx["social_productivity"][PROGRESS_COL].delete_many({"challenge_id": challenge_id})
    mongo.cx["social_productivity"][CHALLENGES_COL].delete_one({"_id": ObjectId(challenge_id)})

    flash("Challenge deleted successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/challenge/<challenge_id>/join")
@login_required
def join_challenge(challenge_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    existing = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id
    })
    if existing:
        flash("You already joined this challenge!", "warning")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    mongo.cx["social_productivity"][JOINS_COL].insert_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id,
        "joined_at": utcnow()
    })
    mongo.cx["social_productivity"][CHALLENGES_COL].update_one(
        {"_id": ObjectId(challenge_id)},
        {"$inc": {"participants_count": 1}}
    )
    flash("You joined the challenge!", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))

@app.route("/challenge/<challenge_id>/remove/<user_id>")
@login_required
def remove_participant(challenge_id, user_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    if challenge.get("created_by") != session["user_id"]:
        flash("Only the challenge creator can remove participants!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    result = mongo.cx["social_productivity"][JOINS_COL].delete_one({
        "user_id": user_id,
        "challenge_id": challenge_id
    })
    if result.deleted_count == 0:
        flash("User is not a participant!", "info")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    mongo.cx["social_productivity"][CHALLENGES_COL].update_one(
        {"_id": ObjectId(challenge_id)},
        {"$inc": {"participants_count": -1}}
    )
    flash("Participant removed from the challenge.", "info")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))

@app.route("/challenge/<challenge_id>/invite/<user_id>")
@login_required
def invite_user(challenge_id, user_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    is_participant = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id
    }) is not None
    if not is_participant:
        flash("Only participants can invite users!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    user_to_invite = get_user_by_id(user_id)
    if not user_to_invite:
        flash("User not found!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    existing = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": user_id,
        "challenge_id": challenge_id
    })
    if existing:
        flash("User is already a participant!", "info")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    mongo.cx["social_productivity"][JOINS_COL].insert_one({
        "user_id": user_id,
        "challenge_id": challenge_id,
        "joined_at": utcnow()
    })
    mongo.cx["social_productivity"][CHALLENGES_COL].update_one(
        {"_id": ObjectId(challenge_id)},
        {"$inc": {"participants_count": 1}}
    )
    flash(f"Invited {user_to_invite['username']} to the challenge!", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))

@app.route("/challenge/<challenge_id>/invite-by-username", methods=["POST"])
@login_required
def invite_by_username(challenge_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    is_participant = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id
    }) is not None
    if not is_participant:
        flash("Only participants can invite users!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    username = request.form.get("username", "").strip()
    if not username:
        flash("Please enter a username!", "warning")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    user_to_invite = get_user_by_username(username)
    if not user_to_invite:
        flash(f"User '{username}' not found!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    existing = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": str(user_to_invite["_id"]),
        "challenge_id": challenge_id
    })
    if existing:
        flash(f"{username} is already a participant!", "info")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    mongo.cx["social_productivity"][JOINS_COL].insert_one({
        "user_id": str(user_to_invite["_id"]),
        "challenge_id": challenge_id,
        "joined_at": utcnow()
    })
    mongo.cx["social_productivity"][CHALLENGES_COL].update_one(
        {"_id": ObjectId(challenge_id)},
        {"$inc": {"participants_count": 1}}
    )
    flash(f"Invited {username} to the challenge!", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))

@app.route("/challenge/<challenge_id>/progress", methods=["POST"])
@login_required
def log_progress(challenge_id):
    challenge = mongo.cx["social_productivity"][CHALLENGES_COL].find_one({"_id": ObjectId(challenge_id)})
    if not challenge:
        flash("Challenge not found!", "danger")
        return redirect(url_for("dashboard"))

    is_participant = mongo.cx["social_productivity"][JOINS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id
    }) is not None
    if not is_participant:
        flash("You are not a participant in this challenge!", "danger")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    today = utcnow().strftime("%Y-%m-%d")
    action = request.form.get("action")
    hours = request.form.get("hours", 0, type=float)
    proof = request.form.get("proof", "").strip()
    file = request.files.get("proof_image")

    if hours < 0:
        hours = 0

    existing = mongo.cx["social_productivity"][PROGRESS_COL].find_one({
        "user_id": session["user_id"],
        "challenge_id": challenge_id,
        "date": today
    })

    if action == "checkin":
        if existing and existing.get("completed"):
            flash("You already checked in today!", "info")
        else:
            if hours <= 0:
                flash("Please enter hours worked (must be > 0)!", "warning")
                return redirect(url_for("challenge_detail", challenge_id=challenge_id))
            if not proof:
                flash("Please describe what you accomplished today!", "warning")
                return redirect(url_for("challenge_detail", challenge_id=challenge_id))
            image_filename = ""
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash("Image must be PNG, JPG, JPEG, GIF, or WEBP!", "warning")
                    return redirect(url_for("challenge_detail", challenge_id=challenge_id))
                filename = secure_filename(f"{session['user_id']}_{today}_{file.filename}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                image_filename = filename
            else:
                flash("Please upload an image proof of your work!", "warning")
                return redirect(url_for("challenge_detail", challenge_id=challenge_id))
            if existing:
                old_image = existing.get("image_filename", "")
                if old_image:
                    old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_image)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                mongo.cx["social_productivity"][PROGRESS_COL].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"completed": True, "hours": hours, "proof": proof, "image_filename": image_filename, "updated_at": utcnow()}}
                )
            else:
                mongo.cx["social_productivity"][PROGRESS_COL].insert_one({
                    "user_id": session["user_id"],
                    "challenge_id": challenge_id,
                    "date": today,
                    "completed": True,
                    "hours": hours,
                    "proof": proof,
                    "image_filename": image_filename,
                    "created_at": utcnow()
                })
            points = int(hours * 10)
            mongo.cx["social_productivity"][USERS_COL].update_one(
                {"_id": ObjectId(session["user_id"])},
                {"$inc": {"total_points": points}}
            )
            flash(f"Logged {hours}h — {proof[:40]}{'...' if len(proof) > 40 else ''} +{points} pts 🔥", "success")
    elif action == "undo":
        if existing and existing.get("completed"):
            prev_hours = existing.get("hours", 0)
            old_image = existing.get("image_filename", "")
            if old_image:
                old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            mongo.cx["social_productivity"][PROGRESS_COL].update_one(
                {"_id": existing["_id"]},
                {"$set": {"completed": False, "hours": 0, "proof": "", "image_filename": "", "updated_at": utcnow()}}
            )
            points_deducted = int(prev_hours * 10)
            mongo.cx["social_productivity"][USERS_COL].update_one(
                {"_id": ObjectId(session["user_id"])},
                {"$inc": {"total_points": -points_deducted}}
            )
            flash(f"Check-in undone (-{points_deducted} pts).", "info")

    return redirect(url_for("challenge_detail", challenge_id=challenge_id))

def calculate_streak(user_id, challenge_id):
    records = list(mongo.cx["social_productivity"][PROGRESS_COL].find({
        "user_id": user_id,
        "challenge_id": challenge_id,
        "completed": True,
        "hours": {"$gt": 0},
        "image_filename": {"$exists": True, "$ne": ""}
    }).sort("date", -1))

    if not records:
        return 0

    streak = 0
    check_date = utcnow()

    for i in range(365):
        date_str = check_date.strftime("%Y-%m-%d")
        found = any(r["date"] == date_str for r in records)
        if found:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            if i == 0:
                check_date -= timedelta(days=1)
                continue
            break

    return streak

@app.route("/leaderboard")
@login_required
def leaderboard():
    users = list(mongo.cx["social_productivity"][USERS_COL].find().sort("total_points", -1))
    all_challenges = list(mongo.cx["social_productivity"][CHALLENGES_COL].find({"is_active": True}).sort("created_at", -1))

    leaderboard_list = []
    for rank, u in enumerate(users, 1):
        if not u.get("username"):
            continue
        leaderboard_list.append({
            "rank": rank,
            "username": u["username"],
            "points": u.get("total_points", 0),
            "challenges_completed": u.get("challenges_completed", 0),
            "created_at": u.get("created_at", utcnow())
        })

    return render_template("leaderboard.html",
                         leaderboard=leaderboard_list[:50],
                         challenges=all_challenges)

@app.route("/profile")
@login_required
def profile():
    user = get_user_by_id(session["user_id"])
    total_checkins = mongo.cx["social_productivity"][PROGRESS_COL].count_documents({
        "user_id": session["user_id"],
        "completed": True
    })
    active_challenges = mongo.cx["social_productivity"][CHALLENGES_COL].count_documents({
        "is_active": True,
        "_id": {"$in": [
            ObjectId(j["challenge_id"])
            for j in mongo.cx["social_productivity"][JOINS_COL].find({"user_id": session["user_id"]})
        ]}
    })
    return render_template("profile.html", user=user, total_checkins=total_checkins, active_challenges=active_challenges)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
