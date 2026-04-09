class Section:
    def __init__(self, name, shape, area, weight, I, W, section_class):
        self.name = name
        self.shape = shape
        self.area = float(area)
        self.weight = float(weight)
        self.I = float(I)
        self.W = float(W)
        self.section_class = section_class

    def __str__(self):
        return (
            f"Section(name={self.name}, shape={self.shape}, area={self.area}, "
            f"weight={self.weight}, I={self.I}, W={self.W}, class={self.section_class})"
        )