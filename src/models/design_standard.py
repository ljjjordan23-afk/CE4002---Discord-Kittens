class DesignStandard:
    def __init__(self, code, alpha, beta):
        self.code = code
        self.alpha = float(alpha)
        self.beta = float(beta)

    def factored_load(self, dead_load, live_load):
        return self.alpha * dead_load + self.beta * live_load

    def __str__(self):
        return f"DesignStandard(code={self.code}, alpha={self.alpha}, beta={self.beta})"