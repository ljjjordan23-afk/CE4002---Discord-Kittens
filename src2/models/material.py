class Material:
    def __init__(self, grade, fy, cost):
        self.grade = grade
        self.fy = float(fy)
        self.cost = float(cost)

    def __str__(self):
        return f"Material(grade={self.grade}, fy={self.fy}, cost={self.cost})"