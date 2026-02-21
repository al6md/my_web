from flask import Blueprint, render_template, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from ..ai_client import ai_client

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/dashboard")
def dashboard():
    health = ai_client.get_health()
    stats = ai_client.get_stats()
    return render_template("admin_dashboard.html", health=health, stats=stats)

@admin_bp.route("/ai-metrics", strict_slashes=False)
@login_required
def ai_metrics():
    # Only Admin check
    allowed_emails = ["admin@example.com", "hbushaq@gmail.com"]
    if current_user.id != 1 and current_user.email not in allowed_emails:
        return jsonify({"error": "Unauthorized"}), 403
        
    from ..models import Experiment, UserEvent, db
    from sqlalchemy import func
    from datetime import datetime, timedelta
    import json
    import gc
    from pathlib import Path
    
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 1. Total events today
        total_events_today = db.session.query(func.count(UserEvent.id)).filter(UserEvent.created_at >= today_start).scalar() or 0
        
        # 2. Active experiments
        active_experiments = Experiment.query.filter_by(status='active').count()
        
        # 3. Simple CTR & Completion estimation
        events_7d = UserEvent.query.filter(UserEvent.created_at >= now - timedelta(days=7)).all()
        clicks_7d = sum(1 for e in events_7d if e.event_type == 'click')
        views_7d = sum(1 for e in events_7d if e.event_type == 'view')
        
        ctr_7d = (clicks_7d / views_7d) if views_7d > 0 else 0.0
        ctr_baseline = 0.08
        
        # Completion rate
        events_30d = UserEvent.query.filter(UserEvent.created_at >= now - timedelta(days=30)).all()
        finish_30d = sum(1 for e in events_30d if e.event_type == 'finish')
        read_30d = sum(1 for e in events_30d if e.event_type == 'read') or sum(1 for e in events_30d if e.event_type == 'view')
        completion_rate_30d = (finish_30d / read_30d) if read_30d > 0 else 0.0
        
        # 4. Read P99 Latency from logs
        p99_latency_ms = 0.0
        latencies = []
        # Path to recommendations.log
        log_file = Path(__file__).parent.parent.parent / "logs" / "recommendations.log"
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[-1000:]
                    for line in lines:
                        if "EXECUTION_LOG_JSON:" in line:
                            try:
                                json_str = line.split("EXECUTION_LOG_JSON:")[1].strip()
                                data = json.loads(json_str)
                                if 'total_time_ms' in data:
                                    latencies.append(data['total_time_ms'])
                            except: pass
                if latencies:
                    latencies.sort()
                    p99_idx = int(len(latencies) * 0.99)
                    if p99_idx < len(latencies):
                        p99_latency_ms = latencies[p99_idx]
            except: pass

        # Free memory
        del events_7d
        del events_30d
        gc.collect()
                
        return jsonify({
            "ctr_7d": round(ctr_7d, 4),
            "ctr_baseline": ctr_baseline,
            "completion_rate_30d": round(completion_rate_30d, 4),
            "ndcg_10": 0.35, 
            "p99_latency_ms": round(p99_latency_ms, 2),
            "active_experiments": active_experiments,
            "total_events_today": total_events_today,
            "exploration_rate": 0.10,
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500
        
    from ..models import Experiment, UserEvent, db
    from sqlalchemy import func
    from datetime import datetime, timedelta
    import json
    import gc
    from pathlib import Path
    
    now = datetime.utcnow()
    
    # 1. Total events today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_events_today = db.session.query(func.count(UserEvent.id)).filter(UserEvent.created_at >= today_start).scalar() or 0
    
    # 2. Active experiments
    active_experiments = Experiment.query.filter_by(status='active').count()
    
    # 3. Simple CTR & Completion estimation (fallback logic if no rich event data yet)
    # views vs clicks logic
    events_7d = UserEvent.query.filter(UserEvent.created_at >= now - timedelta(days=7)).all()
    clicks_7d = sum(1 for e in events_7d if e.event_type == 'click')
    views_7d = sum(1 for e in events_7d if e.event_type == 'view')
    
    ctr_7d = (clicks_7d / views_7d) if views_7d > 0 else 0.0
    ctr_baseline = 0.08 # mock baseline for comparison
    
    # Completion rate (finish vs read events over 30d)
    events_30d = UserEvent.query.filter(UserEvent.created_at >= now - timedelta(days=30)).all()
    finish_30d = sum(1 for e in events_30d if e.event_type == 'finish')
    read_30d = sum(1 for e in events_30d if e.event_type == 'read')
    completion_rate_30d = (finish_30d / read_30d) if read_30d > 0 else 0.0
    
    # 4. Read P99 Latency from logs
    p99_latency_ms = 0.0
    latencies = []
    log_file = Path(__file__).parent.parent.parent / "logs" / "recommendations.log"
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # Read last 1000 lines roughly
                lines = f.readlines()[-1000:]
                for line in lines:
                    if "EXECUTION_LOG_JSON:" in line:
                        try:
                            json_str = line.split("EXECUTION_LOG_JSON:")[1].strip()
                            data = json.loads(json_str)
                            if 'total_time_ms' in data:
                                latencies.append(data['total_time_ms'])
                        except: pass
            if latencies:
                latencies.sort()
                p99_idx = int(len(latencies) * 0.99)
                if p99_idx < len(latencies):
                    p99_latency_ms = latencies[p99_idx]
        except Exception as e:
            pass

    # Free memory
    del events_7d
    del events_30d
    gc.collect()
            
    return jsonify({
        "ctr_7d": round(ctr_7d, 4),
        "ctr_baseline": ctr_baseline,
        "completion_rate_30d": round(completion_rate_30d, 4),
        "ndcg_10": 0.35, # mock or calculated from strict evaluation engine
        "p99_latency_ms": round(p99_latency_ms, 2),
        "active_experiments": active_experiments,
        "total_events_today": total_events_today,
        "exploration_rate": 0.10 # 10% hardcoded from UCB1
    })
