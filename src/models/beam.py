from src.models.member import Member


class Beam(Member):
    def max_moment(self, w, L):
        # M = wL^2 / 12
        return w * (L ** 2) / 12

    def max_stress(self, w, L):
        # sigma = M / W
        # W in x10^3 mm^3 from your Excel
        # Convert kN*m to N*mm: multiply by 10^6
        M = self.max_moment(w, L) * 1e6
        W = self.section.W * 1e3

        return M / W

    def utilization(self, w, L):
        sigma = self.max_stress(w, L)
        return sigma / self.material.fy