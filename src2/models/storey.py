class Storey:
    def __init__(self, level, height, dead_load, live_load, beam, column_left, column_right):
        self.level = int(level)
        self.height = float(height)
        self.dead_load = float(dead_load)
        self.live_load = float(live_load)
        self.beam = beam
        self.column_left = column_left
        self.column_right = column_right

    def design_load(self, design_standard):
        return design_standard.factored_load(self.dead_load, self.live_load)

    def __str__(self):
        return (
            f"Storey(level={self.level}, height={self.height}, "
            f"dead_load={self.dead_load}, live_load={self.live_load}, "
            f"beam={self.beam.section.name}, "
            f"column_left={self.column_left.section.name}, "
            f"column_right={self.column_right.section.name})"
        )