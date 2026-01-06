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
    graph_img = create_mulambo_graph(params)
    
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

def create_mulambo_graph(params):
    # Retrieve dates from params or default to current year
    today = datetime.datetime.now()
    
    start_date_str = params.get('start_date')
    end_date_str = params.get('end_date')
    
    if start_date_str:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
    else:
        start_date = datetime.datetime(today.year, 1, 1)
        
    if end_date_str:
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
        # Adjust end_date to end of day to include workouts on that day if needed?
        # Actually our workouts are timestamps, so we just compare.
        end_date = end_date.replace(hour=23, minute=59, second=59)
    else:
        end_date = datetime.datetime(today.year, 12, 31, 23, 59, 59)

    # Fetch Data
    db = get_db()
    cursor = db.execute('SELECT timestamp FROM workouts ORDER BY timestamp ASC')
    # Parse timestamps. UTC in DB.
    workouts = []
    for row in cursor.fetchall():
        try:
            ts = row['timestamp']
            if isinstance(ts, str):
                workouts.append(datetime.datetime.fromisoformat(ts))
            else:
                workouts.append(ts)
        except ValueError:
            pass
            
    # X Axis: Days from start_date to end_date
    delta_days = (end_date - start_date).days + 1
    if delta_days <= 0: delta_days = 1
    
    # We plot the full range to show "projection" (Potencial)
    day_range = [start_date + datetime.timedelta(days=x) for x in range(delta_days)]
    
    # Pre-calculate workout dates in range
    # Workouts are UTC. Assuming user operates in local or similar. 
    # For simplicity, we just check date equality.
    workout_dates = set(w.date() for w in workouts)
    
    # --- Current Index & Potential Index Calculations ---
    
    # Calculate totals for the bar chart
    workouts_in_period = 0
    for w in workouts:
        if start_date <= w <= end_date:
            workouts_in_period += 1
            
    # Current Index
    # 1 - (workouts / total_days)
    current_idx = 1.0 - (workouts_in_period / float(delta_days))
    if current_idx < 0: current_idx = 0.0
    
    # Potential Index (Min possible index)
    # If I workout every remaining day from TODAY until end_date
    days_remaining = (end_date - today).days
    if days_remaining < 0: days_remaining = 0
    
    # If end_date < today, potential = current (we can't change the past)
    potential_total_workouts = workouts_in_period + days_remaining
    potential_idx = 1.0 - (potential_total_workouts / float(delta_days))
    if potential_idx < 0: potential_idx = 0.0

    # --- Historic General Index ---
    # 1 - Total Workouts (All time) / Total Days (Since first workout ever)
    if not workouts:
        ig_val_str = "N/A"
    else:
        first_w = workouts[0]
        total_days_hist = (today - first_w).days + 1
        if total_days_hist < 1: total_days_hist = 1
        total_n = len(workouts)
        hist_idx_val = 1.0 - (total_n / float(total_days_hist))
        ig_val_str = f"{hist_idx_val:.4f}"

    # Construct Info Text
    s_date_str = start_date.strftime('%d/%m/%y')
    e_date_str = end_date.strftime('%d/%m/%y')
    
    info_text = (
        f"IG: {ig_val_str}\n"
        f"Período: {s_date_str} - {e_date_str}\n"
        f"Treinos: {workouts_in_period} / Potencial: {potential_total_workouts}"
    )

    # Plot Bar Chart
    fig, ax = plt.subplots(figsize=(5, 3), dpi=100)
    fig.patch.set_alpha(1.0) # White background
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    bars = ['Atual', 'Potencial']
    values = [current_idx, potential_idx]
    colors = ['red', 'green']
    
    bar_plot = ax.bar(bars, values, color=colors, width=0.5)
    
    # Add values on top of bars
    for rect in bar_plot:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., height,
                f'{height:.4f}',
                ha='center', va='bottom', fontsize=10, color='black')
    
    # Add Info Text
    ax.text(0.98, 0.98, info_text, transform=ax.transAxes, 
            fontsize=7, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='#ffffcc', alpha=0.9))
    
    ax.set_ylim(0, 1.1) # little extra space for text
    ax.set_title("Índice de Mulambo", fontsize=12, fontweight='bold', color='black')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    
    # Style axis
    ax.tick_params(axis='x', colors='black', labelsize=10)
    ax.tick_params(axis='y', colors='black', labelsize=8)
    ax.spines['bottom'].set_color('black')
    ax.spines['top'].set_color('black')
    ax.spines['left'].set_color('black')
    ax.spines['right'].set_color('black')
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=False)
    buf.seek(0)
    img = Image.open(buf)
    
    plt.close(fig)
    return img

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
