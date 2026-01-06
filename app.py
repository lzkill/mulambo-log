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
    
    # --- Current Index & Potential Index ---
    y_current = []
    y_potential = []
    days_plotted = []
    
    # Count workouts strictly within the selected period until "now"
    cumulative_workouts = 0
    
    for d in day_range:
        # We only plot "Current" line up until Today (or end of range, whichever creates visual sense)
        # If range is fully in past, we plot all. If range is future, we stop at today.
        
        # If day is in future (relative to today), we stop plotting "Current" line
        # but keep plotting "Potential" (if we want to show trajectory).
        is_future = d > today
        
        days_plotted.append(d)
        
        if not is_future:
            if d.date() in workout_dates:
                cumulative_workouts += 1
            
            # Current Index = 1 - (n / m)
            # n = cumulative workouts in period so far
            # m = total days in the selected period (CONSTANT for standard metric? Or growing?)
            # Usually Mulambo Index is annual. m=365.
            # Here m = total days of selected period.
            idx = 1.0 - (cumulative_workouts / float(delta_days))
            y_current.append(idx)
        else:
            y_current.append(None) # Break line
            
        # Potential Index Logic
        # "Max index configurable if I work out every remaining day in the period"
        # At day d, I have done 'cumulative_workouts' (if d <= today)
        # Remaining days = (end_date - d).days
        # Potential Total N = cumulative_workouts + Remaining Days
        # Potential Index = 1 - (PotTotalN / delta_days)
        
        # Note: If d is in future, we assume we HAVE worked out today? 
        # Or do we base potential on "current reality"?
        # Potential usually connects from Current.
        # Let's assume for future points D' > today:
        # We haven't done them yet. So we start counting from TODAY's cumulative.
        # So Potential at D' > Today = (CurrentCum + (DaysBetween Today and End)) ?
        # Actually Potential line is "The Ceiling".
        # It represents: "If I miss zero more workouts from THIS POINT ON".
        
        # Calculation for point d:
        # Days passed in period (inclusive d): (d - start_date).days + 1
        # Days remaining in period (after d): (end_date - d).days
        # But we know workouts only up to min(d, today).
        
        # Let's simplify: At any point d (past or future), the "Maximum Potential Index"
        # represents the index I would get if I had worked out everyday from d+1 until end_date,
        # GIVEN what I did up to d.
        # BUT if d is in future, I don't know what I did.
        # So usually "Potential" is projected from TODAY.
        # i.e. "From today onwards, if I do everything perfect, where do I land?" -> Straight line to target.
        # However, the requirement says "linha 2: índice de mulambo anual máximo que ainda pode ser alcançado"
        # This implies a time series.
        # In the past (d < today): "Back then, what was my max potential?"
        #   It was (workouts_upto_d + days_remaining_after_d) / total.
        
        # Calculate workouts up to d (if d > today, use today's count? No, that assumes misses.)
        # If d > today, Max Potential implies I worked out on d too.
        # So for future d, we imply perfect attendance from today.
        
        cnt_at_d = 0
        if d <= today:
            # Re-count strictly? We have cumulative_workouts iterating.
            # If d is today or past, cumulative_workouts is correct count up to d.
            cnt_at_d = cumulative_workouts
            days_rem = (end_date - d).days
            if days_rem < 0: days_rem = 0
            
            pot_n = cnt_at_d + days_rem # Existing + All Future
            pot_idx = 1.0 - (pot_n / float(delta_days))
            y_potential.append(pot_idx)
        else:
            # Feature: Future Projection
            # If I am at d (future), and I haven't missed any since today.
            # My count would be: (TodayCount) + (Days from Today+1 to d)
            # And remaining is: (end_date - d).days
            # Sum = TodayCount + (d - today) + (end - d) 
            #     = TodayCount + (end - today)
            # It's a constant value! The "Max Potential Endpoint".
            # Because for every future day I work out, n increases by 1 and rem decreases by 1. Sum is constant.
            
            # Use count up to Today
            # We need the count at 'today' specifically.
            # Since 'cumulative_workouts' stops incrementing if d > today in the loop (because d not in workout_dates usually, or controlled),
            # we need to ensure we use the 'cumulative_workouts' snapshot at today.
            
            # Since the loop goes day by day, once we pass today, cumulative_workouts holds the count of workouts up to today.
            # Perfect.
            
            # So for future d:
            # Assume we DON'T miss any future workout.
            # So n increases with d.
            # But the formula (n + rem) stays constant.
            # So the line should be flat for the future?
            # Yes. "The max index achievable" stays constant if we don't miss days.
            # It only drops (worsens) when we MISS a day.
            
            days_rem_from_now = (end_date - today).days
            if days_rem_from_now < 0: days_rem_from_now = 0
            
            # Actually, `cumulative_workouts` here is the count up to today. 
            # Wait, `delta_days` is based on start_date/end_date.
            # We need to make sure `cumulative_workouts` only counts range. It does.
             
            final_pot_n = cumulative_workouts + days_rem_from_now
            final_pot_idx = 1.0 - (final_pot_n / float(delta_days))
            y_potential.append(final_pot_idx)
            
    
    # --- Historic General Index ---
    # 1 - Total Workouts (All time) / Total Days (Since first workout ever)
    # This is a single text value.
    if not workouts:
        historic_text = "Histórico Geral: N/A"
    else:
        first_w = workouts[0]
        # total_m = days since first workout to NOW (or end of data?)
        # Usually "History" implies up to now.
        total_days_hist = (today - first_w).days + 1
        if total_days_hist < 1: total_days_hist = 1
        
        # total_n = all workouts
        total_n = len(workouts)
        
        hist_idx_val = 1.0 - (total_n / float(total_days_hist))
        historic_text = f"IG: {hist_idx_val:.4f}"

    # Plot
    fig, ax = plt.subplots(figsize=(5, 3), dpi=100)
    fig.patch.set_alpha(1.0) # White background
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    
    ax.plot(days_plotted, y_current, label='Atual', color='red', linewidth=2)
    ax.plot(days_plotted, y_potential, label='Potencial', color='green', linestyle='--')
    # Removed Historic Line
    
    # Add Historic Text
    # Position: Top Right or based on params? Just standard corner.
    ax.text(0.95, 0.95, historic_text, transform=ax.transAxes, 
            fontsize=10, verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.5))
    
    ax.set_ylim(0, 1.0)
    ax.set_title("Índice de Mulambo", fontsize=10, fontweight='bold', color='black')
    ax.legend(fontsize='x-small', loc='lower left')
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
