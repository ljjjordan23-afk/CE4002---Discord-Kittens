import numpy as np
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
    
    def max_deflection(self, w_kN_per_m, span_m):
        """
        Maximum midspan deflection for a fixed-fixed beam under UDL:
            delta = w L^4 / (384 E I)

        Units:
        - w_kN_per_m in kN/m
        - span_m in m
        - E in MPa = N/mm^2
        - I stored in x10^6 mm^4 from Excel

        Output:
        - deflection in mm
        """
        E_MPa = 210000.0

        w_N_per_mm = w_kN_per_m      # 1 kN/m = 1 N/mm
        L_mm = span_m * 1000.0
        I_mm4 = self.section.I * 1e6

        delta_mm = (w_N_per_mm * (L_mm ** 4)) / (384 * E_MPa * I_mm4)
        return delta_mm
    
    def beam_diagram_data(self, w_kN_per_m, span_m, n_points=200):
        """
        Returns x positions and values for:
        - shear force diagram (kN)
        - bending moment diagram (kN*m)
        - deflection curve (mm)

        Assumes a fixed-fixed beam under UDL, consistent with
        the simplified project brief using M_max = wL^2 / 12. :contentReference[oaicite:0]{index=0}
        """
        E_MPa = 210000.0
        I_mm4 = self.section.I * 1e6

        x_m = np.linspace(0.0, span_m, n_points)
        L = span_m
        w = w_kN_per_m

        # SFD in kN
        # V(x) = w(L/2 - x)
        V_kN = w * (L / 2.0 - x_m)

        # BMD in kN*m
        # M(x) = -wL^2/12 + (wL/2)x - (w/2)x^2
        M_kNm = -(w * L**2) / 12.0 + (w * L * x_m) / 2.0 - (w * x_m**2) / 2.0

        # Deflection in mm
        # y(x) = w x^2 (L - x)^2 / (24 E I)
        x_mm = x_m * 1000.0
        L_mm = span_m * 1000.0
        w_N_per_mm = w_kN_per_m  # 1 kN/m = 1 N/mm

        y_mm = (
            w_N_per_mm
            * (x_mm ** 2)
            * ((L_mm - x_mm) ** 2)
            / (24.0 * E_MPa * I_mm4)
        )

        return {
            "x_m": x_m,
            "V_kN": V_kN,
            "M_kNm": M_kNm,
            "y_mm": y_mm,
        }