from flask import Flask, jsonify, request
from flask_cors import CORS
import asyncio
import logging
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import unified system
# Note: In a real environment, you would import from the installed package
try:
    from ai_engine.unified_engine import get_unified_engine
    from ai_engine.config.unified_config import get_config
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# Load configuration
config = get_config('production')

# Initialize unified engine
# We use an async loop for the engine initialization if needed, 
# but get_unified_engine is sync in this singleton pattern.
engine = get_unified_engine()


@app.route('/api/recommendations', methods=['POST'])
async def get_recommendations():
    """
    Main recommendations endpoint
    
    POST /api/recommendations
    {
        "user_id": 123,
        "limit": 30,
        "context": {
            "time_of_day": "evening",
            "device": "mobile"
        },
        "fetch_from_internet": true
    }
    """
    try:
        data = request.get_json()
        
        # Helper to run async method from sync Flask route if not using Quart/AsyncFlask properly
        # However, Flask 2.0+ supports async routes natively.
        
        result = await engine.get_recommendations(
            user_id=data.get('user_id'),
            limit=data.get('limit', 30),
            context=data.get('context'),
            # fetch_from_internet=data.get('fetch_from_internet', False) 
            # Note: fetch_from_internet argument depends on implementation in unified_engine.py
        )
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommendations/refresh', methods=['POST'])
async def refresh_recommendations():
    """Force refresh (clear cache)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        
        # Clear cache logic would go here
        # await engine.cache.delete_pattern(f"rec:user_{user_id}*")
        
        # Get fresh recommendations
        result = await engine.get_recommendations(
            user_id=user_id,
            limit=data.get('limit', 30)
        )
        
        return jsonify(result), 200
    except Exception as e:
         return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # specific stats methods depend on implementation
    return jsonify({
        'status': 'healthy',
        'service': 'Unified Recommendation Engine Example'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
