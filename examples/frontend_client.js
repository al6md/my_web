// recommendations.js - Frontend JavaScript Example

class RecommendationService {
    constructor(apiBaseUrl) {
        this.baseUrl = apiBaseUrl;
        this.cache = new Map();
    }

    async getRecommendations(userId, options = {}) {
        const {
            limit = 30,
            offset = 0,
            context = {},
            algorithms = null,
            fetchFromInternet = false,
            searchQuery = null,
            useCache = true
        } = options;

        // Cache Key Generation
        const cacheKey = JSON.stringify({ userId, ...options });

        if (useCache && this.cache.has(cacheKey)) {
            console.log('Cache HIT');
            return this.cache.get(cacheKey);
        }

        // Prepare request
        const body = {
            user_id: userId,
            limit,
            offset,
            context: {
                time_of_day: this._getTimeOfDay(),
                device: this._getDeviceType(),
                ...context
            },
            algorithms,
            fetch_from_internet: fetchFromInternet,
            search_query: searchQuery
        };

        try {
            const response = await fetch(`${this.baseUrl}/api/recommendations/unified`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error('Failed to fetch recommendations');
            }

            const data = await response.json();

            // Store valid result in cache
            if (useCache && data) {
                this.cache.set(cacheKey, data);
                // Simple cache eviction: Clear after 5 mins
                setTimeout(() => this.cache.delete(cacheKey), 5 * 60 * 1000);
            }

            return data;

        } catch (error) {
            console.error(error);
            return null;
        }
    }

    _getTimeOfDay() {
        const hour = new Date().getHours();
        if (hour < 12) return 'morning';
        if (hour < 18) return 'afternoon';
        return 'evening';
    }

    _getDeviceType() {
        const ua = navigator.userAgent;
        if (/mobile/i.test(ua)) return 'mobile';
        if (/tablet/i.test(ua)) return 'tablet';
        return 'desktop';
    }
}

// Usage Example
// const service = new RecommendationService('http://localhost:5000');
// service.getRecommendations(123, { limit: 10 }).then(console.log);
