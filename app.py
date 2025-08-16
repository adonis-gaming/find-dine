from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import random, string

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

parties = {}

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('create_party')
def create_party(data):
    code = generate_code()
    name = data['name']
    parties[code] = {
        "host": name,
        "members": {request.sid: name},
        "restaurants": [],
        "phase": "lobby",
        "votes": {}
    }
    join_room(code)
    emit("party_created", {"code": code, "host": name, "members": list(parties[code]['members'].values())})

@socketio.on('join_party')
def join_party(data):
    code = data['code']
    name = data['name']
    if code not in parties:
        emit("error", {"message": "Party not found"})
        return
    # Remove old sid if name already exists
    existing_sid = None
    for sid, n in parties[code]['members'].items():
        if n == name:
            existing_sid = sid
            break
    if existing_sid:
        del parties[code]['members'][existing_sid]
    parties[code]['members'][request.sid] = name
    join_room(code)
    phase = parties[code]['phase']
    emit("party_updated", {"host": parties[code]['host'], "members": list(parties[code]['members'].values())}, room=code)
    if phase == "adding":
        emit("adding_phase", room=request.sid)
    elif phase == "voting":
        emit("voting_phase", {"restaurants": [r["name"] for r in parties[code]['restaurants']]}, room=request.sid)
    elif phase == "results":
        winner, votes = calculate_winner(code)
        emit("winner", {"restaurant": winner, "votes": votes}, room=request.sid)

@socketio.on('start_adding')
def start_adding(data):
    code = data['code']
    parties[code]['phase'] = "adding"
    emit("adding_phase", room=code)

@socketio.on('add_restaurant')
def add_restaurant(data):
    code = data['code']
    rest = data['restaurant']
    name = parties[code]['members'][request.sid]
    parties[code]['restaurants'].append({"name": rest, "added_by": name})
    emit("restaurant_list", {"restaurants": parties[code]['restaurants']}, room=code)

@socketio.on('remove_restaurant')
def remove_restaurant(data):
    code = data['code']
    rest = data['restaurant']
    name = parties[code]['members'][request.sid]
    parties[code]['restaurants'] = [r for r in parties[code]['restaurants'] if not (r['name'] == rest and r['added_by'] == name)]
    emit("restaurant_list", {"restaurants": parties[code]['restaurants']}, room=code)

@socketio.on('begin_selection')
def begin_selection(data):
    code = data['code']
    parties[code]['phase'] = "voting"
    emit("voting_phase", {"restaurants": [r["name"] for r in parties[code]['restaurants']]}, room=code)

@socketio.on('submit_vote')
def submit_vote(data):
    code = data['code']
    name = parties[code]['members'][request.sid]
    parties[code]['votes'][name] = data['liked']
    if len(parties[code]['votes']) == len(parties[code]['members']):
        parties[code]['phase'] = "results"
        winner, votes = calculate_winner(code)
        emit("winner", {"restaurant": winner, "votes": votes}, room=code)
    else:
        emit("waiting_for_others", room=request.sid)

def calculate_winner(code):
    tally = {}
    for likes in parties[code]['votes'].values():
        for rest in likes:
            tally[rest] = tally.get(rest, 0) + 1
    if not tally:
        return None, 0
    winner = max(tally, key=tally.get)
    return winner, tally[winner]

@socketio.on('disconnect')
def disconnect():
    for code, party in list(parties.items()):
        if request.sid in party['members']:
            name = party['members'][request.sid]
            del party['members'][request.sid]
            if name == party['host']:
                emit("host_left", {"message": "Host has left. Lobby disbanded."}, room=code)
                del parties[code]
                return
            else:
                emit("party_updated", {"host": party['host'], "members": list(party['members'].values())}, room=code)
            break

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0')

