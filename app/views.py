import os
from app import app, db, login_manager
from datetime import datetime
from flask import flash, g, redirect, render_template, request, session, url_for
from flask.ext.login import login_user, logout_user, current_user, login_required
from sqlalchemy import text
from werkzeug import secure_filename

from .forms import LoginForm
from .models import Device, Game, game_device_link, GameMode, Question, question_answer_link, User
from .utils import allowed_file


@app.before_request
def before_request():
    g.user = current_user

@app.route('/')
@app.route('/home')
def home():
    ''' Home page for application.'''

    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    ''' User login page.'''

    # make sure that user is not already logged in
    if g.user is not None and g.user.is_authenticated:
        return redirect(url_for('home'))

    # instantiate LoginForm
    form = LoginForm()
    # process form submission on POST
    if form.validate_on_submit():
        flash(u'Successfully logged in as %s' % form.user.username)
        session['user_id'] = form.user.id
        session['authenticated'] = True
        # check if user has access to next url
        next = request.args.get('next')

        return redirect(next or url_for('home'))
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    ''' User logout page.'''
    
    logout_user()
    # pop session variables
    session.pop('user_id', None)
    session.pop('authenticated', None)
    flash(u'Successfully logged out.')
    return redirect(url_for('home'))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


@app.route('/games')
def games():
    ''' Choose game mode or edit games if admin.'''
    
    return render_template('games.html')


@app.route('/games/learn')
def learn():
    ''' Listing of learning games.'''

    # Get list of all games of type learning
    games = Game.query.join(GameMode).filter(
                GameMode.mode == "learning").order_by('title')
    return render_template('learning.html', games=games)


@app.route('/games/learn/<int:game_id>')
def learning_game(game_id):
    ''' Format for learning games.'''

    return "Hello, World"


@app.route('/games/challenge')
def challenge():
    ''' Listing of challenge games.'''

    # Get list of all games of type challenge
    games = Game.query.join(GameMode).filter(
                GameMode.mode == "challenge").order_by('title')
    return render_template('challenge.html', games=games)


@app.route('/games/challenge/<int:game_id>')
def challenge_game(game_id):
    ''' Format for challenge games.'''

    return "Hello, World"


@app.route('/games/manage', methods=['GET', 'POST'])
@login_required
def manage_games():
    ''' Links for admins to create, edit or delete games.'''
    
    # if POST request, handle changes
    if request.method == "POST":
        # if a game is to be deleted, get id of game
        if "the_game" in request.form:
            game_id = request.form.get('game_id', type=int)
            game = Game.query.get(game_id)
            title = game.title
            # delete associated game
            db.session.delete(game)
            db.session.commit()
            # report that game was deleted and reload page
            flash(u'Successfully deleted %s.' % title)
            return redirect(url_for('manage_games'))
        # if a game is to be created, make a new game and redirect to its page
        elif "create" in request.form:
            # default to first game mode
            game_mode = GameMode.query.all()[0].id
            game = Game(title="Default", description="default", game_mode=game_mode)
            db.session.add(game)
            db.session.commit()
            # redirect to game's edit page
            return redirect(url_for('edit_game', game_id=game.id))
    # otherwise, get data for template
    else:
        # list all learning games first
        learning_games = Game.query.join(GameMode).filter(
                GameMode.mode == "learning").order_by('title')
        challenge_games = Game.query.join(GameMode).filter(
                GameMode.mode == "challenge").order_by('title')
        return render_template('manage_games.html',
                learning_games=learning_games,
                challenge_games=challenge_games)


@app.route('/games/manage/<int:game_id>', methods=['GET', 'POST'])
@login_required
def edit_game(game_id):
    ''' Interface for admin to create or edit games.'''

    # if POST, handle edits
    if request.method == "POST":
        # Get game it exists
        game = Game.query.get_or_404(game_id)
        game_mode = GameMode.query.get_or_404(game.game_mode)
        # Check if game mode needs to be changed
        if "change_mode" in request.form:
            mode = request.form.get('mode', type=int)
            # if new mode is present in request, update game mode
            if not mode:
                flash(u'Invalid game mode selected.')
            elif game.game_mode != mode:
                game_mode = GameMode.query.get(mode)
                game.game_mode = game_mode.id
                db.session.commit()
        # Handle adding RFID
        elif "add_rfid" in request.form:
            # Make sure a valid name is entered
            name = request.form.get('device_name', type=str)
            if not name:
                flash(u'Invalid device name.')
                return redirect(url_for('edit_game', game_id=game_id))
            # Make sure a valid description is entered
            description = request.form.get('device_description', type=str)
            if not description:
                flash(u'Invalid device description.')
                return redirect(url_for('edit_game', game_id=game_id))
            # Make sure valid RFID tag is entered
            tag = request.form.get('device_tag', type=str)
            if not tag:
                flash(u'Invalid rfid tag.')
                return redirect(url_for('edit_game', game_id=game_id))
            # Get file to upload
            file = request.files['file']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_loc = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_loc)
            else:
                flash(u'Invalid file.')
                return redirect(url_for('edit_game', game_id=game_id))
            # Now that everything is good, create Device and link it
            device = Device(name=name, description=description, rfid_tag=tag, file_loc=filename)
            db.session.add(device)
            db.session.commit()
            # Add entry to linking table
            device_link = game_device_link.insert().values(game_id=game_id, device_id=device.id)
            db.session.execute(device_link)
            db.session.commit()
        # handle deleting RFID and associated media
        elif "the_device" in request.form:
            # Get rfid to delete
            device_id = request.form.get('device_id', type=int)
            device = Device.query.get(device_id)
            name = device.name
            # get file location to delete
            filename = os.path.join(app.config['UPLOAD_FOLDER'], device.file_loc)
            # try to delete file
            try:
                os.remove(filename)
            except OSError:
                flash(u'File %s does not exist.' % device.file_loc)
            # Delete rfid
            db.session.delete(device)
            db.session.commit()
            flash(u'Successfully deleted %s.' % name) 
        elif "add_question" in request.form:
            pass
        elif "add_answer" in request.form:
            pass
        # if we get here, render GET request
        return redirect(url_for('edit_game', game_id=game_id))
    # otherwise, GET data for template
    else:
        # Get Game and GameMode
        game = Game.query.get(game_id)
        current_mode = GameMode.query.get(game.game_mode)
        # Get all game modes
        game_modes = GameMode.query.order_by('mode').all()
        # Get all RFIDs associated with game
        devices = Device.query.join(Game.devices).filter(
                    Game.id == game_id).all()
        # if game is of type challenge, get questions and answers
        questions = None
        answers = []
        if current_mode.mode == "challenge":
            # Get all Questions associated with game
            questions = Question.query.join(Game).filter(
                    Game.id == game_id).order_by('question')
            # get answers for each question
            for question in questions:
                answers.append(Question.query.join(Question.answers).filter(
                                    Question.id == question.id).all())
        # render template with attributes
        return render_template('edit_games.html',
                    game=game,
                    current_mode=current_mode,
                    game_modes=game_modes,
                    devices=devices,
                    questions=questions,
                    answers=answers)
