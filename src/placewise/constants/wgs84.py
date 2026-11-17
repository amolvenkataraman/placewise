"""WGS84 ellipsoid: the datum GPS, phones and photo EXIF report in."""

A_M = 6378137.0  # semi-major axis (defining)
F = 1 / 298.257223563  # flattening (defining)
B_M = A_M * (1 - F)  # semi-minor axis
E2 = F * (2 - F)  # first eccentricity squared
