class ConsumerNode:
    def __init__(self, locality, population, historical_demand=None):
        self.locality = locality
        # Population is treated as one feature for the ML model, 
        # not the sole determinant of demand.
        self.population = population
        
        # Structure for historical demand data
        # Example: {"tomato": [{"date": "2023-10-01", "quantity": 120}], "onion": [...]}
        self.historical_demand = historical_demand if historical_demand else {}
        
        # Cross-district factors: people near borders might go to neighboring districts
        self.neighbors = []
        
        self.inventory = {}
        self.wastage = []

    def add_neighbor(self, neighbor_node, distance_km):
        """Adds a neighboring district/market to represent cross-border consumer flow."""
        self.neighbors.append({
            "node": neighbor_node,
            "distance": distance_km
        })

    def _prepare_demand_features(self, commodity, date, weather_data=None, events=None):
        """
        Prepares all features (historical lag, calendar, weather, etc.) for the ML model.
        This isolates the data extraction from the prediction logic itself.
        """
        features = {}
        
        # 1. Population feature
        features["population"] = self.population
        
        # 2. Calendar features (Derived from date in real implementation)
        # features["day_of_week"] = date.weekday()
        # features["month"] = date.month
        # features["season"] = get_season(date)
        
        # 3. Lag / Historical features
        # The ML model needs to know previous demand to find trends.
        # features["demand_yesterday"] = self._get_historical_demand(commodity, date - 1 day)
        # features["demand_last_week_same_day"] = self._get_historical_demand(commodity, date - 7 days)
        # features["moving_average_7d"] = ...
        
        # 4. Festival and Event features
        features["is_festival"] = False
        features["festival_intensity"] = 0.0
        
        if events:
            # Check if any event falls on this date
            for event in events:
                if event["date"] == date:
                    features["is_festival"] = True
                    # Event intensity/type passed as a feature for the ML model to learn from
                    features["festival_intensity"] = event.get("intensity", 1.0)
                    break

        # 5. Weather features
        if weather_data:
            features["temperature"] = weather_data.get("temperature")
            features["rainfall"] = weather_data.get("rainfall")
            features["extreme_weather"] = weather_data.get("extreme_weather", False)

        # 6. Cross-district factors
        if self.neighbors:
            features["nearest_neighbor_distance"] = min(n["distance"] for n in self.neighbors)
        else:
            features["nearest_neighbor_distance"] = None

        return features

    def forecast_demand(self, commodity, date, weather_data=None, events=None):
        """
        Forecasts demand for a specific commodity on a given date.
        """
        # Step 1: Prepare the features
        features = self._prepare_demand_features(commodity, date, weather_data, events)
        
        # Step 2: ML Model Prediction
        # In a real setup with a trained model, it would look like this:
        # return ml_model.predict(features)
        
        # --- SYNTHETIC PLACEHOLDER LOGIC ---
        # Since we don't have a trained ML model yet, we use synthetic heuristic logic.
        # This clearly shows the expected behavior for the simulation.
        
        synthetic_base_demand = self.population * 0.05  # Base synthetic demand
        
        # Simulate higher demand during festivals
        if features.get("is_festival"):
            synthetic_base_demand *= 1.4
            
        # Simulate lower demand during extreme weather (fewer people going to market)
        if features.get("extreme_weather"):
            synthetic_base_demand *= 0.8
            
        predicted_demand = synthetic_base_demand
        # -----------------------------------
        
        return predicted_demand

    def receive_consignment(self, consignment):
        """Adds arrived consignment to the local inventory."""
        commodity = consignment['commodity']
        quantity = consignment['quantity']
        self.inventory[commodity] = self.inventory.get(commodity, 0) + quantity

    def compute_gap(self, commodity, predicted_demand):
        """
        Compares predicted demand with arrived inventory.
        Calculates whether the local node has a shortage or surplus.
        """
        arrived_quantity = self.inventory.get(commodity, 0)
        
        # Difference between what arrived and what is demanded
        diff = arrived_quantity - predicted_demand
        
        if diff < 0:
            return {
                "type": "shortage",
                "amount": abs(diff)
            }
        elif diff > 0:
            return {
                "type": "surplus",
                "amount": diff
            }
        else:
            return {
                "type": "balanced",
                "amount": 0
            }

    def record_wastage(self, amount, reason):
        self.wastage.append({
            "amount": amount,
            "reason": reason
        })
