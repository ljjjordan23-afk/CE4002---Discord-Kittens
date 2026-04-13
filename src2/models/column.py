import math
from src.models.member import Member


class Column(Member):
    def max_stress(self, P_kN):
        """
        Axial stress in MPa
        A stored in mm^2
        P in kN -> N
        """
        P_N = P_kN * 1000.0
        A_mm2 = self.section.area
        return P_N / A_mm2

    def axial_utilization(self, P_kN):
        sigma = self.max_stress(P_kN)
        return sigma / self.material.fy

    def buckling_capacity(self, length_m, K=1.0):
        """
        Euler buckling load Pcr in kN

        Uses:
            Pcr = pi^2 E I / (K L)^2

        Assumptions:
        - E = 210000 MPa = N/mm^2
        - I stored in x10^6 mm^4 from Excel
        - pinned-pinned default K = 1.0 unless user changes it
        """
        E_MPa = 210000.0
        I_mm4 = self.section.I * 1e6
        L_mm = length_m * 1000.0
        KL_mm = K * L_mm

        Pcr_N = (math.pi ** 2) * E_MPa * I_mm4 / (KL_mm ** 2)
        Pcr_kN = Pcr_N / 1000.0
        return Pcr_kN

    def buckling_utilization(self, P_kN, length_m, K=1.0):
        Pcr_kN = self.buckling_capacity(length_m, K=K)
        if Pcr_kN <= 0:
            return float("inf")
        return P_kN / Pcr_kN

    def governing_utilization(self, P_kN, length_m, K=1.0):
        axial_u = self.axial_utilization(P_kN)
        buckling_u = self.buckling_utilization(P_kN, length_m, K=K)
        return max(axial_u, buckling_u)