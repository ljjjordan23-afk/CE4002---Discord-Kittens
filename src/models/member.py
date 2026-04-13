class Member:
    def __init__(self, section, material, length, storey):
        self.section = section
        self.material = material
        self.length = float(length)
        self.storey = storey

    def weight(self):
        # section.weight is kg/m
        return self.section.weight * self.length

    def cost(self):
        # cost = weight x cost per kg
        return self.weight() * self.material.cost