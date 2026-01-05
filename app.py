import os
import base64
import io
import datetime
import sqlite3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from PIL import Image
from flask import Flask, render_template, request, jsonify, g

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(app.instance_path, 'mulambo.sqlite')

# Ensure instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL
            )
        ''')
        db.commit()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/result')
def result():
    return render_template('result.html')

@app.route('/record_workout', methods=['POST'])
def record_workout():
    try:
        now = datetime.datetime.utcnow()
        db = get_db()
        db.execute('INSERT INTO workouts (timestamp) VALUES (?)', (now,))
        db.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/process_image', methods=['POST'])
def process_image():
    data = request.json
    image_data = data.get('image') # Base64 string
    graph_params = data.get('graph_params') # {x, y, w, h}
    
    if not image_data:
        return jsonify({'status': 'error', 'message': 'No image data'}), 400

    try:
        final_image_b64 = generate_composite_image(image_data, graph_params)
        return jsonify({'status': 'success', 'image': final_image_b64})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

def generate_composite_image(base64_img, params):
    # Decode image
    # Remove header if present (data:image/png;base64,...)
    if ',' in base64_img:
        base64_img = base64_img.split(',')[1]
        
    image_bytes = base64.b64decode(base64_img)
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    
    # Generate Graph
    graph_img = create_mulambo_graph()
    
    # Resize Graph
    target_w = int(params.get('width', 300))
    target_h = int(params.get('height', 200))
    # Ensure dimensions are valid
    if target_w <= 0: target_w = 300
    if target_h <= 0: target_h = 200
    
    graph_img = graph_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    # Position
    pos_x = int(params.get('x', 10))
    pos_y = int(params.get('y', 10))
    
    # Composite
    # Paste graph onto image. Use graph itself as mask for transparency
    img.paste(graph_img, (pos_x, pos_y), graph_img)
    
    # Return Base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()

def create_mulambo_graph():
    # Fetch Data
    db = get_db()
    cursor = db.execute('SELECT timestamp FROM workouts ORDER BY timestamp ASC')
    # Parse timestamps. UTC in DB.
    workouts = []
    for row in cursor.fetchall():
        try:
            # Handle ISO format 'YYYY-MM-DD HH:MM:SS.ssss' or similar
            # sqlite default is often string
            ts = row['timestamp']
            if isinstance(ts, str):
                workouts.append(datetime.datetime.fromisoformat(ts))
            else:
                workouts.append(ts)
        except ValueError:
            # Fallback for simple date parsing if needed
            pass
            
    today = datetime.datetime.now()
    year_start = datetime.datetime(today.year, 1, 1)
    
    # X Axis: Days of current year up to now (to avoid empty future graph)
    # OR full year to show projection? 
    # Requirement: "eixo y (linha 2): índice ... anual máximo que ainda pode ser alcançado se em todos os dias restantes do ano a pessoa for malhar"
    # To show this "projection" visually, it's nice to see the whole year.
    # But "Historico" and "Current" stop at today.
    # Let's plot the whole year on X axis.
    
    days_in_year = 366 if (today.year % 4 == 0 and today.year % 100 != 0) or (today.year % 400 == 0) else 365
    all_year_days = [year_start + datetime.timedelta(days=x) for x in range(days_in_year)]
    
    y_current = []
    y_potential = []
    
    # Pre-calculate workout dates this year for O(1) lookup
    workout_dates = set()
    for w in workouts:
        if w.year == today.year:
            workout_dates.add(w.date())
            
    cumulative_workouts = 0
    days_plotted = []
    
    current_day_of_year = today.timetuple().tm_yday
    
    # We only plot "Current" line up into Today
    for d in all_year_days:
        if d > today:
            break
            
        days_plotted.append(d)
        if d.date() in workout_dates:
            cumulative_workouts += 1
            
        # Line 1: 1 - n/m (Current Accumulated)
        # n = workouts so far. m = 365.
        # This graph will go down as n increases (Good!)
        # Wait, 1 - n/m start at 1.0 (0 workouts).
        # If I work out, it drops. 
        idx = 1.0 - (cumulative_workouts / float(days_in_year))
        y_current.append(idx)
    
    # Line 2: Max Potential
    # This is a constant value? Or a trajectory?
    # "índice de mulambo anual máximo que ainda pode ser alcançado"
    # This implies calculations based on "If I work out every remaining day".
    # At any point in time 't', the Max Potential is:
    # 1 - (workouts_so_far + remaining_days) / 365
    # Let's plot this curve for the past as well (what my potential was back then).
    
    # We calculate potential for the same range as current
    y_potential_curve = []
    temp_cum = 0
    for d in days_plotted:
        if d.date() in workout_dates:
            temp_cum += 1
        
        d_yday = d.timetuple().tm_yday
        rem = days_in_year - d_yday
        pot_n = temp_cum + rem
        pot_idx = 1.0 - (pot_n / float(days_in_year))
        y_potential_curve.append(pot_idx)

    # Line 3: Historic
    # This uses ALL workouts.
    # 1 - total_n / total_m
    if not workouts:
        y_historic = [1.0] * len(days_plotted)
    else:
        first_workout = workouts[0]
        y_historic = []
        
        # Need cumulative historical count
        # Count prior to year start
        cnt = len([w for w in workouts if w < year_start])
        
        for d in days_plotted:
            if d.date() in workout_dates:
                cnt += 1
            
            # total_m = days since first workout
            total_days_hist = (d - first_workout).days + 1
            if total_days_hist < 1: total_days_hist = 1
            
            h_idx = 1.0 - (cnt / float(total_days_hist))
            y_historic.append(h_idx)

    # Plot
    fig, ax = plt.subplots(figsize=(5, 3), dpi=100)
    fig.patch.set_alpha(1.0) # White background
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    ax.plot(days_plotted, y_current, label='Atual', color='red', linewidth=2)
    ax.plot(days_plotted, y_potential_curve, label='Potencial', color='green', linestyle='--')
    ax.plot(days_plotted, y_historic, label='Histórico', color='blue', linestyle=':')
    
    ax.set_ylim(0, 1.0)
    ax.set_title("Índice de Mulambo", fontsize=10, fontweight='bold', color='black')
    ax.legend(fontsize='x-small')
    ax.grid(True, alpha=0.3)
    
    # Style axis
    ax.tick_params(axis='x', colors='black')
    ax.tick_params(axis='y', colors='black')
    ax.spines['bottom'].set_color('black')
    ax.spines['top'].set_color('black')
    ax.spines['left'].set_color('black')
    ax.spines['right'].set_color('black')
    
    # Format X axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    plt.xticks(rotation=45, fontsize=8)
    plt.yticks(fontsize=8)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=False)
    buf.seek(0)
    img = Image.open(buf)
    
    plt.close(fig)
    return img

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
