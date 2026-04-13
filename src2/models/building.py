class Building:
    def __init__(self, num_storeys, span, storeys):
        self.num_storeys = int(num_storeys)
        self.span = float(span)
        self.storeys = storeys

    def total_cost(self):
        total = 0.0
        for storey in self.storeys:
            total += storey.beam.cost()
            total += storey.column_left.cost()
            total += storey.column_right.cost()
        return total

    def __str__(self):
        return f"Building(num_storeys={self.num_storeys}, span={self.span})"