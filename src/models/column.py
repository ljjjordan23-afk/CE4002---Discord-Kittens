from src.models.member import Member


class Column(Member):
    def max_stress(self, P):
        # P in kN
        # Convert kN to N: multiply by 10^3
        # A in mm^2
        force_N = P * 1e3
        area_mm2 = self.section.area

        return force_N / area_mm2

    def utilization(self, P):
        sigma = self.max_stress(P)
        return sigma / self.material.fy