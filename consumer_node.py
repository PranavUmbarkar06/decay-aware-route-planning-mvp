class ConsumerNode:

    def __init__(self,locality,historical_demand,population)

        self.population=population
        self.historical_demand=historical_demand
        self.locality=locality

        self.inventory={}
        self.wastage=[]

        def forecast_demand(self,date):

            forecast={}

            for commodity, data in self.historical_demands.items():
                forecast[commodity]=sum(data)/len(data)

            return forecast

        def receieve_consignment(self,consignment):
            commodity=consignment['commodity']
            quantity=consignment['quantity']

            self.inventory[commodity]= \ 
                self.inventory.get(commodity,0)+quantity


        def compute_gap(self,forecast):
            gap={}

            for commodity in forecast:
                demand=forecast[commodity]
                arrived=self.inventory.get(commodity,0)

                diff=arrived-demand

                if diff<0:
                    gap[commodity]={
                        "type":"shortage",
                        "amount":abs(diff)
                    }

                elif diff>0:
                    gap[commodity]={
                        "type":"surplus",
                        "amount":diff
                    }
                else:
                    gap[commodity]={
                        "type":"balanced"
                        "amount":0
                    }
                return gap

        def record_wastage(self,amount,reason):
            self.wastage.append({
                "amount":amount
                "reason":reason
            })

