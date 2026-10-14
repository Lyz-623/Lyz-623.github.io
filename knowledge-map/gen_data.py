#!/usr/bin/env python3
"""Generate data.js for the PC-TWINS knowledge map.

All content (modules, checklists, readings, glossary) lives in this file.
Edit it, then run:

    python gen_data.py                # validate and write data.js
    python gen_data.py --check        # validate only, do not write
    python gen_data.py --check-links  # validate, then check every DOI / arXiv ID / URL online

Validation fails loudly (non-zero exit) if the dependency graph has a cycle,
a prerequisite is not in a strictly lower layer, a module has the wrong number
of checklist items / readings / terms, a module has no "首读" reading, the
weekly study load leaves 15-20 h, or an ID is duplicated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data.js"

PLAN = {
    "weeks": 26,
    "hours_min": 15,
    "hours_max": 20,
    "title": "PC-TWINS 学习路线图",
    "audience": "零超快光学基础、数学物理较弱，目标是 6 个月内能理解、搭建、标定并改进 PC-TWINS 装置并开始研究。",
}

LEVELS = ["核心", "熟悉", "了解"]
LEVEL_HINT = {
    "核心": "能推导或计算，并能讲给别人听",
    "熟悉": "知道结论、物理图像或适用条件",
    "了解": "知道它存在，能跑别人的代码或看懂论文中的用法",
}
READING_TYPES = ["教材", "综述", "里程碑论文", "讲义"]
PRIORITIES = ["首读", "重要", "延伸"]
LAYER_NAMES = {
    0: "数学基础",
    1: "物理基础",
    2: "光学与量子工具",
    3: "非线性与响应",
    4: "光谱学语言",
    5: "一维到二维",
    6: "泵浦–探测几何与相位循环",
    7: "PC-TWINS 与数据",
    8: "高级信号与仪器验收",
    9: "研究前沿",
}

# ---------------------------------------------------------------------------
# References. Every entry was checked on 2026-10-14:
#   doi   -> Crossref /works/<doi> (DataCite via doi.org for 10.6082/10.6084)
#   arxiv -> arXiv export API
#   url   -> publisher / course page fetched (HTTP 200)
# status "unverified" is shown on the page as 未能核实.
# ---------------------------------------------------------------------------
REFS = {
    # --- textbooks -----------------------------------------------------------
    "Riley2006": dict(authors="K. F. Riley, M. P. Hobson, S. J. Bence",
                      title="Mathematical Methods for Physics and Engineering (3rd ed.)",
                      venue="Cambridge University Press", year=2006, doi="10.1017/CBO9780511810763"),
    "Boas2006": dict(authors="M. L. Boas", title="Mathematical Methods in the Physical Sciences (3rd ed.)",
                     venue="Wiley", year=2006,
                     url="https://www.wiley.com/en-us/Mathematical+Methods+in+the+Physical+Sciences%2C+3rd+Edition-p-9780471198260",
                     url_expect="Mathematical Methods in the Physical Sciences",
                     note="无 DOI；已核对 Wiley 出版社页面（ISBN 978-0-471-19826-0，页面标注 2005 年 7 月发行）。"),
    "Saleh1991": dict(authors="B. E. A. Saleh, M. C. Teich", title="Fundamentals of Photonics",
                      venue="Wiley", year=1991, doi="10.1002/0471213748"),
    "Griffiths2017": dict(authors="D. J. Griffiths", title="Introduction to Electrodynamics (4th ed.)",
                          venue="Cambridge University Press", year=2017, doi="10.1017/9781108333511"),
    "Griffiths2018": dict(authors="D. J. Griffiths, D. F. Schroeter", title="Introduction to Quantum Mechanics (3rd ed.)",
                          venue="Cambridge University Press", year=2018, doi="10.1017/9781316995433"),
    "Born1999": dict(authors="M. Born, E. Wolf", title="Principles of Optics (7th ed.)",
                     venue="Cambridge University Press", year=1999, doi="10.1017/CBO9781139644181"),
    "GriffithsdeHaseth2007": dict(authors="P. R. Griffiths, J. A. de Haseth", title="Fourier Transform Infrared Spectrometry (2nd ed.)",
                                  venue="Wiley", year=2007, doi="10.1002/047010631X"),
    "Weiner2009": dict(authors="A. M. Weiner", title="Ultrafast Optics", venue="Wiley", year=2009,
                       doi="10.1002/9780470473467"),
    "Diels2006": dict(authors="J.-C. Diels, W. Rudolph", title="Ultrashort Laser Pulse Phenomena (2nd ed.)",
                      venue="Academic Press / Elsevier", year=2006, doi="10.1016/B978-0-12-215493-5.X5000-9"),
    "Boyd2020": dict(authors="R. W. Boyd", title="Nonlinear Optics (4th ed.)", venue="Academic Press / Elsevier",
                     year=2020, doi="10.1016/C2015-0-05510-1"),
    "Trebino2000": dict(authors="R. Trebino", title="Frequency-Resolved Optical Gating: The Measurement of Ultrashort Laser Pulses",
                        venue="Springer", year=2000, doi="10.1007/978-1-4615-1181-6"),
    "Hamm2011": dict(authors="P. Hamm, M. Zanni", title="Concepts and Methods of 2D Infrared Spectroscopy",
                     venue="Cambridge University Press", year=2011, doi="10.1017/CBO9780511675935"),
    "Mukamel1995": dict(authors="S. Mukamel", title="Principles of Nonlinear Optical Spectroscopy",
                        venue="Oxford University Press", year=1995,
                        url="https://openlibrary.org/isbn/9780195092783",
                        url_check="https://openlibrary.org/isbn/9780195092783.json", url_expect="Oxford University Press",
                        status="unverified",
                        note="无 DOI；OUP 出版社页面拒绝自动访问（HTTP 403），只核对到 Open Library 书目记录（OUP 1995，ISBN 0-19-509278-3）。"),
    # --- lecture notes ---------------------------------------------------------
    "MIT1806": dict(authors="G. Strang", title="18.06 Linear Algebra (Spring 2010), video lectures",
                    venue="MIT OpenCourseWare", year=2010,
                    url="https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/", url_expect="Linear Algebra"),
    "Kartner2005": dict(authors="F. X. Kärtner", title="6.977 Ultrafast Optics (Spring 2005), lecture notes",
                        venue="MIT OpenCourseWare", year=2005,
                        url="https://ocw.mit.edu/courses/6-977-ultrafast-optics-spring-2005/", url_expect="Ultrafast Optics"),
    "Tokmakoff2025": dict(authors="A. Tokmakoff", title="Time-Dependent Quantum Mechanics and Spectroscopy (2025 ed.)",
                          venue="University of Chicago", year=2025, doi="10.6082/uchicago.16831",
                          note="DataCite DOI（非 Crossref）；在线目录 https://tdqms.uchicago.edu/ 。"),
    "Tokmakoff2D": dict(authors="A. Tokmakoff", title="Nonlinear and Two-Dimensional Spectroscopy Notes",
                        venue="University of Chicago", year=2011,
                        url="https://tdqms.uchicago.edu/2d-spectroscopy-notes/", url_expect="Two-Dimensional Spectroscopy"),
    "Shlens2014": dict(authors="J. Shlens", title="A Tutorial on Principal Component Analysis", venue="arXiv",
                       year=2014, arxiv="1404.1100"),
    # --- journal articles ------------------------------------------------------
    "Jones1941": dict(authors="R. C. Jones", title="A New Calculus for the Treatment of Optical Systems. I. Description and Discussion of the Calculus",
                      venue="J. Opt. Soc. Am.", volume="31", pages="488–493", year=1941, doi="10.1364/JOSA.31.000488"),
    "Malitson1965": dict(authors="I. H. Malitson", title="Interspecimen Comparison of the Refractive Index of Fused Silica",
                         venue="J. Opt. Soc. Am.", volume="55", pages="1205–1209", year=1965, doi="10.1364/JOSA.55.001205"),
    "Fork1984": dict(authors="R. L. Fork, O. E. Martinez, J. P. Gordon", title="Negative dispersion using pairs of prisms",
                     venue="Opt. Lett.", volume="9", pages="150", year=1984, doi="10.1364/OL.9.000150"),
    "Strickland1985": dict(authors="D. Strickland, G. Mourou", title="Compression of amplified chirped optical pulses",
                           venue="Opt. Commun.", volume="56", pages="219–221", year=1985, doi="10.1016/0030-4018(85)90120-8"),
    "Trebino1997": dict(authors="R. Trebino et al.", title="Measuring ultrashort laser pulses in the time-frequency domain using frequency-resolved optical gating",
                        venue="Rev. Sci. Instrum.", volume="68", pages="3277–3295", year=1997, doi="10.1063/1.1148286"),
    "Cerullo2003": dict(authors="G. Cerullo, S. De Silvestri", title="Ultrafast optical parametric amplifiers",
                        venue="Rev. Sci. Instrum.", volume="74", pages="1–18", year=2003, doi="10.1063/1.1523642"),
    "Manzoni2016": dict(authors="C. Manzoni, G. Cerullo", title="Design criteria for ultrafast optical parametric amplifiers",
                        venue="J. Opt.", volume="18", pages="103501", year=2016, doi="10.1088/2040-8978/18/10/103501"),
    "Bradler2009": dict(authors="M. Bradler, P. Baum, E. Riedle", title="Femtosecond continuum generation in bulk laser host materials with sub-μJ pump pulses",
                        venue="Appl. Phys. B", volume="97", pages="561–574", year=2009, doi="10.1007/s00340-009-3699-1"),
    "Lindblad1976": dict(authors="G. Lindblad", title="On the generators of quantum dynamical semigroups",
                         venue="Commun. Math. Phys.", volume="48", pages="119–130", year=1976, doi="10.1007/BF01608499"),
    "Mukamel2000": dict(authors="S. Mukamel", title="Multidimensional Femtosecond Correlation Spectroscopies of Electronic and Vibrational Excitations",
                        venue="Annu. Rev. Phys. Chem.", volume="51", pages="691–729", year=2000,
                        doi="10.1146/annurev.physchem.51.1.691"),
    "Kubo1969": dict(authors="R. Kubo", title="A Stochastic Theory of Line Shape",
                     venue="Adv. Chem. Phys.", volume="15", pages="101–127", year=1969, doi="10.1002/9780470143605.ch6"),
    "Hilborn1982": dict(authors="R. C. Hilborn", title="Einstein coefficients, cross sections, f values, dipole moments, and all that",
                        venue="Am. J. Phys.", volume="50", pages="982–986", year=1982, doi="10.1119/1.12937"),
    "Olivero1977": dict(authors="J. J. Olivero, R. L. Longbothum", title="Empirical fits to the Voigt line width: A brief review",
                        venue="J. Quant. Spectrosc. Radiat. Transfer", volume="17", pages="233–236", year=1977,
                        doi="10.1016/0022-4073(77)90161-3"),
    "Lepetit1995": dict(authors="L. Lepetit, G. Chériaux, M. Joffre", title="Linear techniques of phase measurement by femtosecond spectral interferometry for applications in spectroscopy",
                        venue="J. Opt. Soc. Am. B", volume="12", pages="2467", year=1995, doi="10.1364/JOSAB.12.002467"),
    "Brida2012": dict(authors="D. Brida, C. Manzoni, G. Cerullo", title="Phase-locked pulses for two-dimensional spectroscopy by a birefringent delay line",
                      venue="Opt. Lett.", volume="37", pages="3027", year=2012, doi="10.1364/OL.37.003027"),
    "Oriana2016": dict(authors="A. Oriana, J. Réhault, F. Preda, D. Polli, G. Cerullo", title="Scanning Fourier transform spectrometer in the visible range based on birefringent wedges",
                       venue="J. Opt. Soc. Am. A", volume="33", pages="1415", year=2016, doi="10.1364/JOSAA.33.001415"),
    "Preda2017": dict(authors="F. Preda et al.", title="Linear and Nonlinear Spectroscopy by a Common-Path Birefringent Interferometer",
                      venue="IEEE J. Sel. Top. Quantum Electron.", volume="23", pages="88–96", year=2017,
                      doi="10.1109/JSTQE.2016.2630840"),
    "Rehault2014": dict(authors="J. Réhault, M. Maiuri, A. Oriana, G. Cerullo", title="Two-dimensional electronic spectroscopy with birefringent wedges",
                        venue="Rev. Sci. Instrum.", volume="85", pages="123107", year=2014, doi="10.1063/1.4902938"),
    "Berera2009": dict(authors="R. Berera, R. van Grondelle, J. T. M. Kennis", title="Ultrafast transient absorption spectroscopy: principles and application to photosynthetic systems",
                       venue="Photosynth. Res.", volume="101", pages="105–118", year=2009, doi="10.1007/s11120-009-9454-y"),
    "Megerle2009": dict(authors="U. Megerle et al.", title="Sub-50 fs broadband absorption spectroscopy with tunable excitation: putting the analysis of ultrafast molecular dynamics on solid ground",
                        venue="Appl. Phys. B", volume="96", pages="215–231", year=2009, doi="10.1007/s00340-009-3610-0"),
    "Lorenc2002": dict(authors="M. Lorenc et al.", title="Artifacts in femtosecond transient absorption spectroscopy",
                       venue="Appl. Phys. B", volume="74", pages="19–27", year=2002, doi="10.1007/s003400100750"),
    "Kovalenko1999": dict(authors="S. A. Kovalenko, A. L. Dobryakov, J. Ruthmann, N. P. Ernsting", title="Femtosecond spectroscopy of condensed phases with chirped supercontinuum probing",
                          venue="Phys. Rev. A", volume="59", pages="2369–2384", year=1999, doi="10.1103/PhysRevA.59.2369"),
    "Branczyk2014": dict(authors="A. M. Brańczyk, D. B. Turner, G. D. Scholes", title="Crossing disciplines – A view on two-dimensional optical spectroscopy",
                         venue="Ann. Phys. (Berlin)", volume="526", pages="31–49", year=2014, doi="10.1002/andp.201300153"),
    "Jonas2003": dict(authors="D. M. Jonas", title="Two-Dimensional Femtosecond Spectroscopy",
                      venue="Annu. Rev. Phys. Chem.", volume="54", pages="425–463", year=2003,
                      doi="10.1146/annurev.physchem.54.011002.103907"),
    "Cundiff2013": dict(authors="S. T. Cundiff, S. Mukamel", title="Optical multidimensional coherent spectroscopy",
                        venue="Phys. Today", volume="66", pages="44–49", year=2013, doi="10.1063/PT.3.2047"),
    "Hybl1998": dict(authors="J. D. Hybl, A. W. Albrecht, S. M. Gallagher Faeder, D. M. Jonas", title="Two-dimensional electronic spectroscopy",
                     venue="Chem. Phys. Lett.", volume="297", pages="307–313", year=1998, doi="10.1016/S0009-2614(98)01140-3"),
    "Khalil2003": dict(authors="M. Khalil, N. Demirdöven, A. Tokmakoff", title="Obtaining Absorptive Line Shapes in Two-Dimensional Infrared Vibrational Correlation Spectra",
                       venue="Phys. Rev. Lett.", volume="90", pages="047401", year=2003, doi="10.1103/PhysRevLett.90.047401"),
    "Brixner2005": dict(authors="T. Brixner et al.", title="Two-dimensional spectroscopy of electronic couplings in photosynthesis",
                        venue="Nature", volume="434", pages="625–628", year=2005, doi="10.1038/nature03429"),
    "Butkus2012": dict(authors="V. Butkus, D. Zigmantas, L. Valkunas, D. Abramavicius", title="Vibrational vs. electronic coherences in 2D spectrum of molecular systems",
                       venue="Chem. Phys. Lett.", volume="545", pages="40–43", year=2012, doi="10.1016/j.cplett.2012.07.014"),
    "Shim2009": dict(authors="S.-H. Shim, M. T. Zanni", title="How to turn your pump–probe instrument into a multidimensional spectrometer: 2D IR and Vis spectroscopies via pulse shaping",
                     venue="Phys. Chem. Chem. Phys.", volume="11", pages="748–761", year=2009, doi="10.1039/B813817F"),
    "Fuller2015": dict(authors="F. D. Fuller, J. P. Ogilvie", title="Experimental Implementations of Two-Dimensional Fourier Transform Electronic Spectroscopy",
                       venue="Annu. Rev. Phys. Chem.", volume="66", pages="667–690", year=2015,
                       doi="10.1146/annurev-physchem-040513-103623"),
    "Myers2008": dict(authors="J. A. Myers, K. L. M. Lewis, P. F. Tekavec, J. P. Ogilvie", title="Two-color two-dimensional Fourier transform electronic spectroscopy with a pulse-shaper",
                      venue="Opt. Express", volume="16", pages="17420", year=2008, doi="10.1364/OE.16.017420"),
    "Yan2009": dict(authors="S. Yan, H.-S. Tan", title="Phase cycling schemes for two-dimensional optical spectroscopy with a pump–probe beam geometry",
                    venue="Chem. Phys.", volume="360", pages="110–115", year=2009, doi="10.1016/j.chemphys.2009.04.019"),
    "Tan2008": dict(authors="H.-S. Tan", title="Theory and phase-cycling scheme selection principles of collinear phase coherent multi-dimensional optical spectroscopy",
                    venue="J. Chem. Phys.", volume="129", pages="124501", year=2008, doi="10.1063/1.2978381"),
    "Zhang2012": dict(authors="Z. Zhang, K. L. Wells, E. W. J. Hyland, H.-S. Tan", title="Phase-cycling schemes for pump–probe beam geometry two-dimensional electronic spectroscopy",
                      venue="Chem. Phys. Lett.", volume="550", pages="156–161", year=2012, doi="10.1016/j.cplett.2012.08.037"),
    "Bodenhausen1984": dict(authors="G. Bodenhausen, H. Kogler, R. R. Ernst", title="Selection of coherence-transfer pathways in NMR pulse experiments",
                            venue="J. Magn. Reson.", volume="58", pages="370–388", year=1984, doi="10.1016/0022-2364(84)90142-2"),
    "Levitt2002": dict(authors="M. H. Levitt, P. K. Madhu, C. E. Hughes", title="Cogwheel Phase Cycling",
                       venue="J. Magn. Reson.", volume="155", pages="300–306", year=2002, doi="10.1006/jmre.2002.2520"),
    "Timmer2024": dict(authors="D. Timmer, D. Lünemann, M. Gittinger, A. De Sio, C. Manzoni, G. Cerullo, C. Lienau",
                       title="Phase-cycling and double-quantum two-dimensional electronic spectroscopy using a common-path birefringent interferometer",
                       venue="Optica", volume="11", pages="1646", year=2024, doi="10.1364/OPTICA.543007", arxiv="2409.11959"),
    "Timmer2024SI": dict(authors="D. Timmer et al.", title="Supplementary document for Phase-cycling and double-quantum two-dimensional electronic spectroscopy using a common-path birefringent interferometer",
                         venue="Optica Publishing Group (figshare)", year=2025, doi="10.6084/m9.figshare.27853911",
                         note="figshare 托管的补充材料。"),
    "Timmer2025": dict(authors="D. Timmer, D. Lünemann, A. De Sio, G. Cerullo et al.", title="Disentangling signal contributions in two-dimensional electronic spectroscopy in the pump–probe geometry",
                       venue="J. Chem. Phys.", volume="162", pages="124202", year=2025, doi="10.1063/5.0256813"),
    "Cai2024": dict(authors="M.-R. Cai, X. Zhang, Z.-Q. Cheng, T.-F. Yan, H. Dong", title="Extracting double-quantum coherence in two-dimensional electronic spectroscopy under pump–probe geometry",
                    venue="Rev. Sci. Instrum.", volume="95", pages="033006", year=2024, doi="10.1063/5.0198255"),
    "Kim2009": dict(authors="J. Kim, S. Mukamel, G. D. Scholes", title="Two-Dimensional Electronic Double-Quantum Coherence Spectroscopy",
                    venue="Acc. Chem. Res.", volume="42", pages="1375–1384", year=2009, doi="10.1021/ar9000795"),
    "Stone2009": dict(authors="K. W. Stone et al.", title="Two-Quantum 2D FT Electronic Spectroscopy of Biexcitons in GaAs Quantum Wells",
                      venue="Science", volume="324", pages="1169–1173", year=2009, doi="10.1126/science.1170274"),
    "Turner2010": dict(authors="D. B. Turner, K. A. Nelson", title="Coherent measurements of high-order electronic correlations in quantum wells",
                       venue="Nature", volume="466", pages="1089–1092", year=2010, doi="10.1038/nature09286"),
    "Luttig2023": dict(authors="J. Lüttig et al.", title="Higher-Order Multidimensional and Pump–Probe Spectroscopies",
                       venue="J. Phys. Chem. Lett.", volume="14", pages="7556–7573", year=2023, doi="10.1021/acs.jpclett.3c01694"),
    "Krich2025": dict(authors="J. J. Krich et al.", title="Separating Orders of Response in Transient Absorption and Coherent Multidimensional Spectroscopy by Intensity Variation",
                      venue="J. Phys. Chem. Lett.", volume="16", pages="5897–5905", year=2025, doi="10.1021/acs.jpclett.5c01177"),
    "Yetzbacher2007": dict(authors="M. K. Yetzbacher, N. Belabas, K. A. Kitney, D. M. Jonas", title="Propagation, beam geometry, and detection distortions of peak shapes in two-dimensional Fourier transform spectra",
                           venue="J. Chem. Phys.", volume="126", pages="044511", year=2007, doi="10.1063/1.2426337"),
    "Bloem2010": dict(authors="R. Bloem, S. Garrett-Roe, H. Strzalka, P. Hamm, P. Donaldson", title="Enhancing signal detection and completely eliminating scattering using quasi-phase-cycling in 2D IR experiments",
                      venue="Opt. Express", volume="18", pages="27067", year=2010, doi="10.1364/OE.18.027067"),
    "Bruder2018": dict(authors="L. Bruder, M. Binz, F. Stienkemeier", title="Phase-synchronous undersampling in nonlinear spectroscopy",
                       venue="Opt. Lett.", volume="43", pages="875", year=2018, doi="10.1364/OL.43.000875"),
    "vanStokkum2004": dict(authors="I. H. M. van Stokkum, D. S. Larsen, R. van Grondelle", title="Global and target analysis of time-resolved spectra",
                           venue="Biochim. Biophys. Acta – Bioenerg.", volume="1657", pages="82–104", year=2004,
                           doi="10.1016/j.bbabio.2004.04.011"),
    "Kwak2007": dict(authors="K. Kwak, S. Park, I. J. Finkelstein, M. D. Fayer", title="Frequency-frequency correlation functions and apodization in two-dimensional infrared vibrational echo spectroscopy: A new approach",
                     venue="J. Chem. Phys.", volume="127", pages="124503", year=2007, doi="10.1063/1.2772269"),
    "Jolliffe2016": dict(authors="I. T. Jolliffe, J. Cadima", title="Principal component analysis: a review and recent developments",
                         venue="Phil. Trans. R. Soc. A", volume="374", pages="20150202", year=2016, doi="10.1098/rsta.2015.0202"),
    "Biswas2022": dict(authors="S. Biswas, J. Kim, X. Zhang, G. D. Scholes", title="Coherent Two-Dimensional and Broadband Electronic Spectroscopies",
                       venue="Chem. Rev.", volume="122", pages="4257–4321", year=2022, doi="10.1021/acs.chemrev.1c00623"),
    "Draeger2017": dict(authors="S. Draeger, S. Roeding, T. Brixner", title="Rapid-scan coherent 2D fluorescence spectroscopy",
                        venue="Opt. Express", volume="25", pages="3259", year=2017, doi="10.1364/OE.25.003259"),
    "Richter2017": dict(authors="J. M. Richter et al.", title="Ultrafast carrier thermalization in lead iodide perovskite probed with two-dimensional electronic spectroscopy",
                        venue="Nat. Commun.", volume="8", pages="376", year=2017, doi="10.1038/s41467-017-00546-z"),
}


def R(key, rtype, priority, part, why):
    """One recommended reading: reference key + type + priority + which part + why."""
    return dict(ref=key, type=rtype, priority=priority, part=part, why=why)


def C(level, text, key=None):
    """One checklist item. `key` keeps saved progress if you later reword `text`."""
    return dict(level=level, text=text, key=key)


def T(zh, en, definition):
    return dict(zh=zh, en=en, definition=definition)


# ---------------------------------------------------------------------------
# Modules. weeks = (first, last) week of the 26-week plan; hours = total study
# hours, spread evenly over those weeks when checking the weekly load.
# ---------------------------------------------------------------------------
MODULES = [
    dict(
        id="F1", zh="复数、相量与线性代数", en="Complex numbers, phasors & linear algebra", short="复数与线性代数",
        layer=0, prereqs=[], chapters=[1, 2], weeks=(1, 2), hours=20,
        why="光场、相位和量子态都用复数与矩阵书写，后面每一个推导都默认你会算复指数和矩阵乘法。",
        checklist=[
            C("核心", "能把 A cos(ωt + φ) 写成复相量形式，并用相量相加算出两束同频光叠加后的振幅与相位"),
            C("核心", "能用欧拉公式推导 |e^{iα} + e^{iβ}|² = 2 + 2cos(α − β)，并指出其中的干涉项"),
            C("核心", "能手算 2×2 矩阵的乘积、逆、行列式以及本征值和本征向量"),
            C("熟悉", "能说明厄米矩阵的本征值为实数、本征向量互相正交，并指出它对应物理可观测量"),
            C("熟悉", "能写出幺正矩阵的定义 U†U = I，并验证一个 2×2 旋转矩阵是幺正的"),
            C("熟悉", "能用 numpy.linalg.eig 求矩阵的本征分解，并数值验证 A v = λ v"),
            C("了解", "知道张量积（Kronecker 积）用于组合两个子系统的态空间，能用 numpy.kron 构造它"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", "第 3 章 Complex numbers and hyperbolic functions（pp. 83–114）；第 8 章 Matrices and vector spaces（pp. 241–315）中本征值、厄米与幺正矩阵各节",
              "从零讲起、例题密集，适合补基础；只读与清单对应的小节即可。"),
            R("Boas2006", "教材", "重要", "第 3 章（线性代数：矩阵、线性向量空间与矩阵对角化）",
              "比 Riley 更口语化，作为同一内容的第二种讲法；卡住时换着读。"),
            R("MIT1806", "讲义", "延伸", "讲本征值、对角化与对称矩阵的几讲视频",
              "Strang 的课程以几何直觉见长，适合在通勤时补看。"),
        ],
        terms=[
            T("相量", "phasor", "把同频振荡 A cos(ωt + φ) 记作复数 A e^{iφ}，加法和求导变成复数运算。"),
            T("欧拉公式", "Euler's formula", "e^{iθ} = cos θ + i sin θ，连接复指数与三角函数。"),
            T("本征值", "eigenvalue", "满足 A v = λ v 的数 λ；对厄米算符而言就是可能的测量结果。"),
            T("厄米矩阵", "Hermitian matrix", "等于自身共轭转置的矩阵（A = A†），本征值全为实数。"),
            T("幺正矩阵", "unitary matrix", "满足 U†U = I 的矩阵，保持内积与概率守恒，描述无损演化。"),
        ],
    ),
    dict(
        id="F2", zh="微积分、常微分方程与概率统计", en="Calculus, ODEs & probability", short="微积分与概率",
        layer=0, prereqs=[], chapters=[3], weeks=(1, 2), hours=16,
        why="布居与相干的演化是一阶线性微分方程，噪声与误差棒靠概率统计，两者从 Bloch 方程一直用到数据分析。",
        checklist=[
            C("核心", "能用积分因子法解 dy/dt = −y/T + f(t)，并画出指数衰减与阶跃响应"),
            C("核心", "能解阻尼谐振子方程，写出欠阻尼时的振荡频率与衰减时间"),
            C("核心", "能计算一组测量的均值、标准差与均值标准误，并说明平均 N 次后噪声按 1/√N 下降的前提（独立同分布）"),
            C("熟悉", "能写出高斯分布与泊松分布，并说明光子计数的散粒噪声为何服从泊松统计"),
            C("熟悉", "能做误差传递：已知 x、y 的不确定度，估算 x/y 与 ln x 的不确定度"),
            C("熟悉", "能计算高斯积分 ∫exp(−ax²)dx，并由高斯函数的 σ 求出 FWHM = 2√(2 ln 2) σ"),
            C("了解", "知道 scipy.integrate.solve_ivp 可以数值解常微分方程，能用它复现解析的指数衰减"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", "第 14–15 章 First-order / Higher-order ODEs（pp. 468–530）；第 30–31 章 Probability, Statistics（pp. 1119–1304）中基本分布与误差各节",
              "一本书覆盖本模块全部数学；概率统计只读常用分布、期望方差与误差传递。"),
            R("Boas2006", "教材", "重要", "第 8 章 Ordinary differential equations（第三版把 Laplace 变换与 δ 函数也放在这一章）",
              "δ 函数与 Laplace 变换后面讲冲击响应时会再用到。"),
            R("Tokmakoff2025", "讲义", "延伸", "第 6 章 Classical Description of Spectroscopy（6.2–6.4 受驱阻尼振子与冲击响应）",
              "用阻尼振子的语言提前预告“响应函数”，是从数学走向光谱学的桥。"),
        ],
        terms=[
            T("时间常数", "time constant", "指数衰减 e^{−t/T} 中的 T，信号降到 1/e 所需的时间。"),
            T("标准误", "standard error of the mean", "均值的不确定度 σ/√N，随平均次数增加而减小。"),
            T("散粒噪声", "shot noise", "光子或电子到达的离散性造成的泊松噪声，相对涨落为 1/√N。"),
            T("误差传递", "error propagation", "由输入量的不确定度经一阶偏导估计输出量不确定度的方法。"),
        ],
    ),
    dict(
        id="F3", zh="傅里叶变换与离散采样", en="Fourier transform & discrete sampling", short="傅里叶与采样",
        layer=1, prereqs=["F1", "F2"], chapters=[4], weeks=(3, 4), hours=18,
        why="2DES 的激发频率轴就是对延迟做傅里叶变换得到的；步长、扫描长度与窗函数直接决定谱的范围、分辨率与假峰。",
        checklist=[
            C("核心", "能推导高斯脉冲的傅里叶变换，并验证 FWHM 时间带宽积 ΔtΔν = 2 ln 2/π ≈ 0.441"),
            C("核心", "能由 Nyquist 条件算出覆盖给定光频范围所需的最大延迟步长，并说明欠采样时谱峰如何折叠"),
            C("核心", "能由最大扫描延迟 T_max 估算频率分辨率 δν ≈ 1/T_max，并用它估算 2DES 激发轴的分辨率"),
            C("熟悉", "能用卷积定理说明切趾（窗函数）如何以分辨率换取更低的旁瓣"),
            C("熟悉", "能用 numpy.fft 对衰减余弦做 FFT，用 fftfreq 与 fftshift 正确构造频率轴并认出正负频率"),
            C("熟悉", "能说明零填充只是在频域插值，不能提高真实分辨率"),
            C("了解", "知道因果信号的实部与虚部互相决定（Hilbert 变换 / Kramers–Kronig），后面恢复复信号时会用到"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", "第 13 章 Integral transforms（pp. 433–467）：Fourier 变换、δ 函数、卷积定理与 Parseval 定理",
              "把连续傅里叶变换的定义与常用定理一次学全。"),
            R("GriffithsdeHaseth2007", "教材", "重要", "第 3 章 Sampling the Interferogram（pp. 57–74）；第 4 章 Fourier Transforms（pp. 75–95）",
              "FTIR 与 TWINS 激发轴同为“对干涉图采样再做 FT”，Nyquist、混叠与切趾的实际处理讲得最实用。"),
            R("Hamm2011", "教材", "延伸", "附录 Fourier transformation（pp. 254–259）",
              "多维光谱语境下的 FT 约定与离散 FT 要点，篇幅很短。"),
        ],
        terms=[
            T("时间带宽积", "time–bandwidth product", "脉冲时域宽度与频域宽度之积，存在由脉冲形状决定的下限。"),
            T("奈奎斯特频率", "Nyquist frequency", "采样率的一半；高于它的频率成分会被折叠到低频。"),
            T("混叠", "aliasing", "采样不足时高频信号被错误地映射到低频位置的现象。"),
            T("切趾", "apodization", "对有限长数据乘窗函数以压低截断带来的旁瓣，代价是峰变宽。"),
            T("零填充", "zero padding", "在时域数据后补零以加密频率采样点，不增加信息量。"),
            T("卷积定理", "convolution theorem", "时域卷积对应频域相乘，反之亦然。"),
        ],
    ),
    dict(
        id="F4", zh="电磁波、偏振与双折射", en="EM waves, polarization & birefringence", short="偏振与双折射",
        layer=1, prereqs=["F1"], chapters=[5, 6, 7], weeks=(3, 4), hours=18,
        why="TWINS 的核心是双折射楔片：o 光与 e 光的群速度差产生可控延迟，偏振投影决定相位；不会 Jones 演算就读不懂 PC-TWINS。",
        checklist=[
            C("核心", "能从 Maxwell 方程推出介质中的平面波解，写出 k = nω/c 与光强 I ∝ n|E|²"),
            C("核心", "能写出任意方位角下线偏振片、λ/2 与 λ/4 波片的 Jones 矩阵，并算出偏振态经过多个元件后的输出"),
            C("核心", "能算出厚度 L 的单轴晶体中 o 光与 e 光的相位差 Δφ = 2π(n_e − n_o)L/λ，并区分相位延迟与群延迟"),
            C("熟悉", "能说明光轴、o 光与 e 光的定义，以及光轴方位怎样决定入射偏振被分解成哪两个分量"),
            C("熟悉", "能区分相折射率 n 与群折射率 n_g = n − λ dn/dλ，并用 Sellmeier 公式数值计算熔融石英的 n_g"),
            C("熟悉", "能说明两块光轴互相垂直的双折射晶体为何可以互相抵消延迟（这是 TWINS 可调过零延迟的出发点）"),
            C("了解", "知道 α-BBO 为中心对称结构、用作双折射元件，β-BBO 无中心对称、用于倍频，二者不可混用"),
        ],
        readings=[
            R("Saleh1991", "教材", "首读", "第 6 章 Polarization and Crystal Optics（pp. 193–237）：Jones 矩阵、波片、单轴晶体",
              "偏振与晶体光学一章讲透，图示清楚，直接对应 TWINS 需要的全部工具。"),
            R("Griffiths2017", "教材", "重要", "第 9 章 Electromagnetic Waves（pp. 382–435）",
              "从 Maxwell 方程到平面波、能流与介质中传播的标准推导。"),
            R("Jones1941", "里程碑论文", "延伸", "第 I 部分：Jones 演算的定义与讨论",
              "Jones 演算的原始论文，看看矩阵方法最初是怎样提出的。"),
            R("Malitson1965", "里程碑论文", "延伸", "熔融石英的 Sellmeier 色散公式与系数表",
              "计算群折射率与 GDD 时最常用的材料数据来源。"),
        ],
        terms=[
            T("Jones 矩阵", "Jones matrix", "作用在二维复偏振矢量上的 2×2 矩阵，描述偏振元件对完全偏振光的作用。"),
            T("双折射", "birefringence", "折射率随偏振方向不同的性质，使两个正交偏振分量获得不同的相位与群延迟。"),
            T("寻常光 / 非常光", "ordinary / extraordinary ray", "单轴晶体中偏振垂直于 / 处在光轴与波矢平面内的两个本征偏振分量。"),
            T("群折射率", "group index", "n_g = n − λ dn/dλ，决定脉冲包络的传播速度 c/n_g。"),
            T("波片", "wave plate", "利用双折射在两正交偏振间引入固定相位差（如 π 或 π/2）的元件。"),
        ],
    ),
    dict(
        id="F5", zh="量子力学基础与二能级体系", en="Quantum mechanics basics & two-level systems", short="二能级量子体系",
        layer=1, prereqs=["F1", "F2"], chapters=[15], weeks=(5, 6), hours=18,
        why="2DES 把电子跃迁抽象为二能级或三能级体系；跃迁偶极、叠加态与 Rabi 振荡是所有响应函数的出发点。",
        checklist=[
            C("核心", "能写出二能级体系的哈密顿量，并求出定态能量与本征态"),
            C("核心", "能由含时薛定谔方程推出叠加态系数按 e^{−iEt/ħ} 演化，并说明相对相位以跃迁频率 ω_eg 振荡"),
            C("核心", "能在旋转波近似下推导共振 Rabi 振荡 P_e(t) = sin²(Ωt/2)"),
            C("熟悉", "能用 Dirac 记号计算偶极期望值 ⟨ψ|μ|ψ⟩，并说明只有存在相干叠加时它才以 ω_eg 振荡"),
            C("熟悉", "能说明旋转波近似的适用条件（近共振，且 Rabi 频率与失谐都远小于跃迁频率）"),
            C("熟悉", "能区分本征态、叠加态与测量概率（Born 规则）"),
            C("了解", "知道弱场下 Rabi 振荡的小角度极限就是微扰区，2DES 的三阶信号正是在这一区间定义的"),
        ],
        readings=[
            R("Griffiths2018", "教材", "首读", "第 3 章 Formalism（pp. 91–130）；第 11 章 Quantum Dynamics（pp. 402–445）中二能级体系与含时微扰各节",
              "Dirac 记号与二能级动力学的入门标准读物，难度适合零基础。"),
            R("Tokmakoff2025", "讲义", "重要", "第 2 章 2.3 Two-Level System；第 3 章 3.4 Resonant Driving of a Two-Level System 与 3.5 The Interaction Picture",
              "面向光谱学的写法，直接为后面的相互作用绘景与响应函数铺路。"),
        ],
        terms=[
            T("二能级体系", "two-level system", "只保留基态 |g⟩ 与激发态 |e⟩ 的最简量子模型。"),
            T("跃迁偶极矩", "transition dipole moment", "μ_eg = ⟨e|μ|g⟩，决定跃迁与光耦合的强弱和偏振取向。"),
            T("Rabi 频率", "Rabi frequency", "Ω = μ_eg E/ħ，共振驱动下布居在两能级间往返的角频率。"),
            T("旋转波近似", "rotating-wave approximation", "忽略以约 2ω 快速振荡的反共振项的近似。"),
            T("叠加态", "superposition state", "c_g|g⟩ + c_e|e⟩ 形式的态，其相对相位携带相干信息。"),
        ],
    ),
    dict(
        id="F6", zh="干涉、相干性与外差探测", en="Interference, coherence & heterodyne detection", short="干涉与外差",
        layer=2, prereqs=["F3", "F4"], chapters=[8], weeks=(5, 8), hours=12,
        why="探测器只能测强度，2DES 的相位信息全靠信号场与参考场（本振）的干涉项读出。",
        checklist=[
            C("核心", "能推导两束光叠加时 I = I₁ + I₂ + 2√(I₁I₂) cos Δφ，并算出条纹可见度"),
            C("核心", "能说明外差探测中弱信号 E_s 与强本振 E_LO 的交叉项 2Re(E_LO* E_s) 如何放大信号并保留相位"),
            C("熟悉", "能由光谱宽度估算相干时间 τ_c ≈ 1/Δν，并说明 Wiener–Khinchin 定理连接自相关与功率谱"),
            C("熟悉", "能说明 Michelson 干涉仪测得的干涉图与光源光谱互为傅里叶变换（傅里叶变换光谱学原理）"),
            C("熟悉", "能估算相位稳定性要求：程差抖动 δL 造成相位误差 2πδL/λ，算出 600 nm 下 λ/100 稳定度对应的位移"),
            C("熟悉", "能说明在泵浦–探测几何中探测光本身充当本振，因此信号自动被外差放大"),
            C("了解", "知道在本振散粒噪声主导时，再增大本振功率不再提高外差信噪比"),
        ],
        readings=[
            R("Saleh1991", "教材", "首读", "第 2 章 Wave Optics（pp. 41–79）中干涉各节；第 10 章 Statistical Optics（pp. 342–383）中时间相干性各节",
              "先建立双光束干涉，再用统计光学定义相干时间。"),
            R("GriffithsdeHaseth2007", "教材", "重要", "第 2 章 Theoretical Background（pp. 19–55）：Michelson 干涉仪与干涉图",
              "干涉图与光谱互为傅里叶变换，这正是 TWINS 测线性光谱与标定延迟的原理。"),
            R("Born1999", "教材", "延伸", "第 7 章 Elements of the theory of interference and interferometers（pp. 286–411）",
              "干涉理论的权威参考，需要严格推导时查阅。"),
        ],
        terms=[
            T("条纹可见度", "fringe visibility", "(I_max − I_min)/(I_max + I_min)，衡量干涉对比度与相干程度。"),
            T("相干时间", "coherence time", "光场保持确定相位关系的时间尺度，约为光谱宽度的倒数。"),
            T("外差探测", "heterodyne detection", "让弱信号与强参考场干涉，通过交叉项测量信号的振幅与相位。"),
            T("本振", "local oscillator", "外差探测中作为相位参考的强场；泵浦–探测几何中由探测光担任。"),
            T("干涉图", "interferogram", "探测强度随延迟变化的曲线，其傅里叶变换给出光谱。"),
        ],
    ),
    dict(
        id="F7", zh="超短脉冲：时频描述、色散与啁啾", en="Ultrashort pulses: time–frequency picture, dispersion & chirp", short="超短脉冲与色散",
        layer=2, prereqs=["F3", "F4"], chapters=[10, 11], weeks=(5, 7), hours=24,
        why="2DES 的时间分辨率与带宽来自飞秒脉冲；光路中每一块玻璃（包括 TWINS 楔片）都会引入色散，必须会算并会补偿。",
        checklist=[
            C("核心", "能写出光谱相位展开 φ(ω) = φ₀ + φ₁(ω−ω₀) + φ₂(ω−ω₀)²/2 + …，并说明 φ₀、群延迟、GDD 与 TOD 各自对时域波形的影响"),
            C("核心", "能计算变换极限高斯脉冲经过 GDD 后的脉宽 τ_out = τ_in √(1 + (4 ln 2 · GDD/τ_in²)²)"),
            C("核心", "能由材料的 GVD（fs²/mm）估算一块熔融石英或 BBO 引入的 GDD 与展宽"),
            C("熟悉", "能说明载波–包络相位在单个脉冲的强度测量中看不到，但在两个脉冲的干涉中决定相对相位"),
            C("熟悉", "能描述棱镜对、光栅对与啁啾镜补偿正色散的原理及各自的优缺点"),
            C("熟悉", "能用 FFT 数值模拟：给光谱加二次相位，得到时域啁啾脉冲并读出瞬时频率"),
            C("了解", "知道自相位调制在无色散时只展宽光谱而不改变脉宽，是白光产生与脉冲压缩的物理基础"),
        ],
        readings=[
            R("Weiner2009", "教材", "首读", "第 1 章 Introduction and Review（pp. 1–31）；第 4 章 Dispersion and Dispersion Compensation（pp. 147–197）",
              "脉冲的时频描述与色散补偿最系统的现代教材。"),
            R("Diels2006", "教材", "重要", "第 1 章 Fundamentals（pp. 1–60）；第 2 章 Femtosecond Optics（pp. 61–142）",
              "相位展开与色散元件的另一种讲法，公式推导更细。"),
            R("Kartner2005", "讲义", "延伸", "讲义第 2–3 章（色散、非线性脉冲传播与脉冲压缩）",
              "免费讲义，适合与教材对照做习题。"),
            R("Fork1984", "里程碑论文", "延伸", "全文（3 页）",
              "棱镜对负色散的原始论文，搭压缩器前读一遍。"),
        ],
        terms=[
            T("变换极限", "transform limit", "给定光谱下可能的最短脉冲，对应平坦（线性）光谱相位。"),
            T("群延迟色散", "group-delay dispersion (GDD)", "光谱相位对频率的二阶导数，单位 fs²，导致脉冲展宽与啁啾。"),
            T("群速度色散", "group-velocity dispersion (GVD)", "单位长度材料的 GDD，单位 fs²/mm。"),
            T("啁啾", "chirp", "脉冲瞬时频率随时间变化的现象，正啁啾时红光在前。"),
            T("载波–包络相位", "carrier–envelope phase (CEP)", "载波峰值相对包络峰值的相位，即光谱相位的常数项 φ₀。"),
        ],
    ),
    dict(
        id="F8", zh="密度矩阵、相干与系综", en="Density matrix, coherence & ensembles", short="密度矩阵",
        layer=2, prereqs=["F5"], chapters=[16], weeks=(7, 8), hours=16,
        why="溶液和固体样品都是系综，必须用密度矩阵描述：对角元是布居、非对角元是相干，2DES 的每条信号路径都是密度矩阵元之间的跳转。",
        checklist=[
            C("核心", "能由纯态构造 ρ = |ψ⟩⟨ψ|，并说出二能级体系 ρ 的四个元素各自的物理意义"),
            C("核心", "能推导 Liouville–von Neumann 方程 dρ/dt = −(i/ħ)[H, ρ]，并说明相干元 ρ_eg 以 e^{−iω_eg t} 演化"),
            C("核心", "能加入唯象的 T₁、T₂ 写出光学 Bloch 方程，并解出自由演化下 ρ_eg(t) 的衰减"),
            C("熟悉", "能用 Tr ρ² 区分纯态与混合态，并说明室温下光学跃迁的热平衡系综几乎全部处于基态"),
            C("熟悉", "能用 P = N Tr(μρ) 计算宏观极化，并说明系综平均为何会造成非均匀退相"),
            C("熟悉", "能写出 1/T₂ = 1/(2T₁) + 1/T₂* 并说明各项的物理来源"),
            C("了解", "知道 Lindblad 主方程是保证 ρ 始终为正的一般马尔可夫弛豫形式"),
        ],
        readings=[
            R("Tokmakoff2025", "讲义", "首读", "第 12 章 12.4 Mixed States、12.5 The Density Matrix、12.6 Time-Dependence of the Density Matrix",
              "为光谱学写的密度矩阵入门，符号与后面的响应函数一致。"),
            R("Boyd2020", "教材", "重要", "第 3 章 Quantum-Mechanical Theory of the Nonlinear Optical Susceptibility（pp. 137–202）中密度矩阵表述各节",
              "用密度矩阵加唯象弛豫计算极化率，直接连到下一层的响应理论。"),
            R("Lindblad1976", "里程碑论文", "延伸", "引言与主定理的形式",
              "知道 Lindblad 形式从哪里来；数学证明可以跳过。"),
        ],
        terms=[
            T("密度矩阵", "density matrix", "ρ = Σ p_i |ψ_i⟩⟨ψ_i|，描述系综（含混合态）的完整量子态。"),
            T("布居", "population", "密度矩阵对角元 ρ_nn，处于能级 n 的概率。"),
            T("相干", "coherence", "密度矩阵非对角元 ρ_nm，以 ω_nm 振荡，是辐射与量子拍的来源。"),
            T("光学 Bloch 方程", "optical Bloch equations", "含 T₁、T₂ 唯象弛豫的二能级密度矩阵运动方程。"),
            T("退相", "dephasing", "相干元因涨落或系综平均而衰减、但布居不变的过程。"),
        ],
    ),
    dict(
        id="F9", zh="非线性光学与脉冲诊断", en="Nonlinear optics & pulse characterisation", short="非线性光学与诊断",
        layer=3, prereqs=["F7"], chapters=[12, 13], weeks=(8, 9), hours=16,
        why="不测脉冲就不知道样品处的时间分辨率；SHG 自相关与 FROG 是每天调光路的工具，也是理解 NOPA 的物理基础。",
        checklist=[
            C("核心", "能写出二阶极化 P⁽²⁾ = ε₀χ⁽²⁾E²，并推出倍频（SHG）与和频（SFG）的频率关系"),
            C("核心", "能推导强度自相关宽度与脉宽的关系，并对高斯脉冲使用 √2 去卷积因子"),
            C("核心", "能用相位匹配条件 Δk = 0 说明晶体角度调谐的作用，并说明为何宽带脉冲需要薄晶体"),
            C("熟悉", "能说明强度自相关为何无法给出光谱相位，而 FROG 通过谱图加相位恢复可以"),
            C("熟悉", "能读懂 SHG-FROG 谱图，并说明其时间方向（啁啾符号）不定性"),
            C("熟悉", "能说明在样品位置测泵浦–探测互相关的意义：它给出仪器响应函数与零时刻"),
            C("了解", "知道 SPIDER 等其他脉冲测量方法的存在及各自测量的物理量"),
        ],
        readings=[
            R("Trebino1997", "综述", "首读", "前半部分：自相关的局限、FROG 原理与各种几何",
              "FROG 发明者写的综述，图例清楚，是脉冲测量的标准入口。"),
            R("Weiner2009", "教材", "重要", "第 3 章 Ultrafast-Pulse Measurement Methods（pp. 85–146）；第 5 章 Ultrafast Nonlinear Optics: Second Order（pp. 198–257）",
              "把脉冲测量与二阶非线性放在同一套符号下讲。"),
            R("Boyd2020", "教材", "重要", "第 1 章 The Nonlinear Optical Susceptibility（pp. 1–64）；第 2 章 Wave-Equation Description（pp. 65–135）中 SHG 与相位匹配各节",
              "非线性极化与相位匹配的标准推导。"),
            R("Trebino2000", "教材", "延伸", "实验装置与相位恢复算法各章",
              "真正动手搭 FROG 或写恢复程序时查阅。"),
        ],
        terms=[
            T("二次谐波", "second-harmonic generation (SHG)", "χ⁽²⁾ 介质中两个 ω 光子合成一个 2ω 光子的过程。"),
            T("相位匹配", "phase matching", "使各频率分量波矢满足 Δk = 0，从而让非线性信号相干累积。"),
            T("强度自相关", "intensity autocorrelation", "脉冲与自身延迟副本的 SHG 信号随延迟的变化，只含脉宽信息。"),
            T("频率分辨光学开关", "FROG", "记录随延迟变化的非线性信号光谱（谱图），再迭代恢复脉冲振幅与相位。"),
            T("仪器响应函数", "instrument response function (IRF)", "泵浦与探测脉冲的互相关，限制可分辨的最快动力学。"),
        ],
    ),
    dict(
        id="F10", zh="微扰理论与非线性响应函数", en="Perturbation theory & nonlinear response functions", short="响应函数",
        layer=3, prereqs=["F3", "F8"], chapters=[17, 18], weeks=(9, 11), hours=27,
        why="2DES 信号就是三阶极化 P⁽³⁾；响应函数把“三个脉冲加等待时间”翻译成可计算的公式，是读懂任何 2DES 理论段落的钥匙。",
        checklist=[
            C("核心", "能在相互作用绘景下对密度矩阵做逐阶展开，写出一阶修正 ρ⁽¹⁾(t) 的积分表达式"),
            C("核心", "能写出线性响应函数，并说明其傅里叶变换给出复极化率 χ⁽¹⁾(ω)，虚部对应吸收"),
            C("核心", "能把 P⁽³⁾(t) 写成 R⁽³⁾(t₃, t₂, t₁) 与三个电场的三重卷积，并说出 t₁、t₂、t₃ 的物理含义"),
            C("熟悉", "能说明 R⁽³⁾ 为何展开为 8 项（4 对 Liouville 路径及其复共轭）"),
            C("熟悉", "能说明冲击极限（脉冲远短于所有动力学）下三重卷积如何简化为响应函数本身"),
            C("熟悉", "能说明因果性 θ(t) 与响应函数实部、虚部之间 Kramers–Kronig 关系的联系"),
            C("了解", "知道在电偶极近似下各向同性介质的偶数阶响应为零，因此溶液中最低阶的非线性信号是三阶"),
        ],
        readings=[
            R("Hamm2011", "教材", "首读", "第 3 章 Mukamelian or perturbative expansion of the density matrix（pp. 48–60）",
              "13 页讲清从密度矩阵到三阶响应函数，是最短的正确入口。"),
            R("Tokmakoff2025", "讲义", "重要", "第 14 章 Linear Response Theory（14.4 Quantum Linear Response Functions、14.5 Nonlinear response functions）",
              "从经典阻尼振子推广到量子响应函数，推导步步可跟。"),
            R("Mukamel2000", "综述", "延伸", "前两节：响应函数框架与多维相关光谱的分类",
              "了解该领域通用的理论语言与符号来源。"),
            R("Mukamel1995", "教材", "延伸", "第 5–6 章（非线性响应函数与 Liouville 空间路径）的相关小节",
              "领域经典专著，作为查阅用；难度高，不建议通读。"),
        ],
        terms=[
            T("相互作用绘景", "interaction picture", "把已知的无微扰演化吸收进算符，只追踪由微扰引起的变化的表象。"),
            T("响应函数", "response function", "把各阶极化与入射电场联系起来的时间核，包含体系的全部动力学。"),
            T("三阶极化", "third-order polarization", "P⁽³⁾，与电场三次方成正比的宏观极化，是泵浦–探测与 2DES 信号的来源。"),
            T("冲击极限", "impulsive limit", "把脉冲近似为 δ 函数的极限，此时信号直接正比于响应函数。"),
            T("极化率", "susceptibility", "χ⁽ⁿ⁾(ω)，响应函数在频域的表示。"),
        ],
    ),
    dict(
        id="F11", zh="谱干涉与 TWINS 双折射干涉仪", en="Spectral interferometry & the TWINS interferometer", short="谱干涉与 TWINS",
        layer=3, prereqs=["F6", "F7"], chapters=[26, 27], weeks=(16, 17), hours=16,
        why="TWINS 用双折射楔片产生相位锁定的泵浦脉冲对，是 PC-TWINS 的心脏；延迟标定依靠谱干涉与傅里叶变换光谱技巧。",
        checklist=[
            C("核心", "能画出 TWINS 光路（偏振片、固定双折射块、一对可平移楔片、投影偏振片），说明两个正交偏振分量如何获得可调并可过零的相对延迟"),
            C("核心", "能由楔角与平移量算出楔片有效厚度的变化，并由 o/e 光群折射率差估算延迟随位置的变化"),
            C("核心", "能用傅里叶变换光谱法标定延迟：记录干涉图对楔片位置的依赖，逐波长求干涉频率，得到位置–延迟换算"),
            C("熟悉", "能说明共光路结构为何使两个脉冲的相对延迟对机械振动与空气扰动不敏感"),
            C("熟悉", "能说明谱干涉条纹间隔 2π/Δt 与延迟的关系，并用傅里叶变换谱干涉（FTSI）提取相位差"),
            C("熟悉", "能说明双折射色散使 TWINS 的相位延迟随波长变化，因此激发轴必须逐波长标定"),
            C("了解", "知道商用 TWINS 器件（NIREOS GEMINI-2D）存在，并可分别用于线性 FT 光谱与 2DES"),
        ],
        readings=[
            R("Brida2012", "里程碑论文", "首读", "全文（3 页）",
              "TWINS 用于二维光谱的原始方案：相位锁定脉冲对如何产生。"),
            R("Lepetit1995", "里程碑论文", "首读", "第 2–3 节：谱干涉原理与 FTSI 相位提取算法",
              "延迟与相位标定所用谱干涉方法的标准参考。"),
            R("Oriana2016", "里程碑论文", "重要", "装置设计与延迟标定各节",
              "楔片 FT 光谱仪的标定流程与 TWINS 完全相同，可直接照做。"),
            R("Preda2017", "综述", "延伸", "全文，重点看 2D 光谱部分",
              "Polimi 组对 TWINS 线性与非线性光谱应用的总结。"),
        ],
        terms=[
            T("TWINS", "Translating-Wedge-based Identical pulses eNcoding System", "基于平移双折射楔片的共光路干涉仪，产生相位锁定的同偏振脉冲对。"),
            T("共光路干涉仪", "common-path interferometer", "两臂光束走同一路径，只靠偏振区分，因而天然相位稳定。"),
            T("双折射楔片", "birefringent wedges", "一对楔形双折射晶体，平移一块即可连续改变有效厚度与延迟。"),
            T("谱干涉", "spectral interferometry", "两个延迟脉冲在光谱仪上形成的频域条纹，携带延迟与相位差信息。"),
            T("延迟标定", "delay calibration", "建立楔片位置与实际延迟（及其波长依赖）之间换算关系的过程。"),
        ],
    ),
    dict(
        id="F12", zh="飞秒光源、NOPA 与光路搭建", en="Femtosecond sources, NOPA & beam delivery", short="光源与 NOPA",
        layer=4, prereqs=["F9"], chapters=[9, 14], weeks=(10, 11), hours=16,
        why="Cerullo 组的 2DES 泵浦与探测通常来自 NOPA 与白光；会估算光斑、聚焦、重叠与激发密度是搭光路的日常。",
        checklist=[
            C("核心", "能用高斯光束公式计算束腰与瑞利长度，并估算透镜焦点处的光斑 w₀ ≈ λf/(πw_in)"),
            C("核心", "能写出光参量放大的能量与动量守恒（ω_p = ω_s + ω_i），并说明非共线几何如何通过信号光与闲频光群速度匹配实现宽带增益"),
            C("熟悉", "能描述啁啾脉冲放大（CPA）的展宽–放大–压缩流程及其目的"),
            C("熟悉", "能说明白光超连续产生的阈值行为，以及介质（如蓝宝石、YAG、CaF₂）对光谱范围与稳定性的影响"),
            C("熟悉", "能由脉冲能量、重复频率与光斑尺寸估算样品处的能流与激发密度，并判断是否处于微扰区"),
            C("熟悉", "能说明锁模的基本思想：纵模之间固定的相位关系产生周期脉冲串"),
            C("了解", "知道 Kerr 透镜锁模是钛宝石振荡器最常用的被动锁模机制"),
        ],
        readings=[
            R("Cerullo2003", "综述", "首读", "OPA 原理与非共线相位匹配各节",
              "导师组的经典综述，NOPA 原理与设计的标准读物。"),
            R("Manzoni2016", "综述", "重要", "全文",
              "以教学方式整理的 OPA 设计准则，比 2003 综述更易读。"),
            R("Saleh1991", "教材", "重要", "第 3 章 Beam Optics（pp. 80–107）",
              "高斯光束、聚焦与 ABCD 传输的标准推导。"),
            R("Bradler2009", "里程碑论文", "延伸", "不同晶体中白光产生的对比结果",
              "选择白光介质与泵浦条件时的实验依据。"),
            R("Strickland1985", "里程碑论文", "延伸", "全文（3 页）",
              "CPA 的原始论文。"),
        ],
        terms=[
            T("非共线光参量放大", "noncollinear optical parametric amplifier (NOPA)", "让泵浦与信号光成一定夹角以实现超宽带相位匹配的参量放大器。"),
            T("啁啾脉冲放大", "chirped-pulse amplification (CPA)", "先展宽脉冲再放大最后压缩，以避免高峰值功率损伤增益介质。"),
            T("超连续白光", "supercontinuum / white light", "强脉冲在透明介质中经非线性过程展宽成的宽带光谱，常作探测光。"),
            T("瑞利长度", "Rayleigh range", "高斯光束光斑面积增大一倍所对应的传播距离 z_R = πw₀²/λ。"),
            T("锁模", "mode-locking", "使激光腔各纵模保持固定相位关系从而输出超短脉冲串的技术。"),
        ],
    ),
    dict(
        id="F13", zh="Liouville 路径与双边费曼图", en="Liouville pathways & double-sided Feynman diagrams", short="双边费曼图",
        layer=4, prereqs=["F10"], chapters=[19], weeks=(12, 13), hours=20,
        why="双边费曼图是 2DES 的“语法”：每个峰、每种相位循环挑出的信号都对应若干张图，PC-TWINS 论文的核心论证都用图写成。",
        checklist=[
            C("核心", "能按规则画出二能级与三能级（含双激发态 f）体系的全部三阶双边费曼图（GSB、SE、ESA）"),
            C("核心", "能由图读出信号的波矢 k_s = ∓k₁ ± k₂ + k₃ 与相位因子，并据此区分 rephasing 与 non-rephasing"),
            C("核心", "能从一张图写出对应的响应函数项：符号、跃迁偶极因子与各时间段的相位演化"),
            C("熟悉", "能说明 ESA 图的符号与 GSB、SE 图相反，因此在吸收型 2D 谱中峰的正负相反"),
            C("熟悉", "能说明为什么在等待时间内处于相干态的图会产生随 t₂ 振荡的量子拍"),
            C("熟悉", "能画出双量子信号对应的图，并指出体系在哪段时间处于 |f⟩⟨g| 相干、其演化频率约为 ω_fg"),
            C("了解", "知道固定时间顺序的图只在脉冲不重叠时成立，脉冲重叠时还要考虑时序交换的额外路径"),
        ],
        readings=[
            R("Hamm2011", "教材", "首读", "第 4 章 Basics of 2D IR spectroscopy（pp. 61–87）",
              "费曼图规则、rephasing / non-rephasing 与吸收型谱讲得最清楚。"),
            R("Tokmakoff2D", "讲义", "重要", "Nonlinear Spectroscopy 部分的 “Diagrammatic Perturbation Theory” 与 “Third-Order Nonlinear Spectroscopies” 两节",
              "免费讲义，配有视频，可作为 Hamm & Zanni 的第二视角。"),
            R("Branczyk2014", "综述", "重要", "费曼图与相位匹配各节",
              "为跨学科读者写的 2D 光谱入门，直观而准确。"),
        ],
        terms=[
            T("双边费曼图", "double-sided Feynman diagram", "用左右两条竖线表示密度矩阵 ket 与 bra 两侧随时间与光场相互作用的图示。"),
            T("Liouville 路径", "Liouville pathway", "密度矩阵在各次相互作用之间经过的一串矩阵元。"),
            T("基态漂白", "ground-state bleach (GSB)", "泵浦使基态布居减少、探测吸收变弱产生的信号。"),
            T("受激发射", "stimulated emission (SE)", "激发态布居在探测光作用下受激辐射产生的信号。"),
            T("激发态吸收", "excited-state absorption (ESA)", "激发态向更高能级吸收探测光产生的信号，符号与 GSB/SE 相反。"),
            T("重相位 / 非重相位", "rephasing / non-rephasing", "t₁ 与 t₃ 期间相干的相位旋转方向相反 / 相同的两类路径。"),
        ],
    ),
    dict(
        id="F14", zh="弛豫、线形与线性吸收", en="Relaxation, lineshapes & linear absorption", short="弛豫与线形",
        layer=4, prereqs=["F10"], chapters=[20, 21], weeks=(12, 14), hours=21,
        why="2D 峰形的对角与反对角宽度分别对应非均匀与均匀展宽，谱扩散让峰形随等待时间变圆；不懂线形就读不出 2D 谱里的动力学。",
        checklist=[
            C("核心", "能推导均匀展宽给出 Lorentz 线形、非均匀展宽给出 Gauss 线形，并写出各自 FWHM 与 T₂、σ 的关系"),
            C("核心", "能用 Beer–Lambert 定律由摩尔吸光系数、浓度与光程计算光密度，并反推所需样品浓度"),
            C("熟悉", "能说明 Kubo 随机线形模型中快调制（运动变窄）与慢调制两个极限"),
            C("熟悉", "能写出频率涨落相关函数 C(t) = ⟨δω(t)δω(0)⟩，并说明它与谱扩散的关系"),
            C("熟悉", "能在跃迁偶极矩、振子强度与 Einstein 系数之间换算"),
            C("熟悉", "能说明 Voigt 线形是 Lorentz 与 Gauss 的卷积，并用经验公式估算其宽度"),
            C("了解", "知道振动结构（Franck–Condon 进程、Huang–Rhys 因子）会在吸收谱上产生振动边带"),
        ],
        readings=[
            R("Tokmakoff2025", "讲义", "首读", "第 15 章 15.4 Line Broadening Mechanisms；第 17 章 Fluctuations and Dephasing（17.1–17.2）",
              "从相关函数出发统一讲线形、退相与谱扩散。"),
            R("Hamm2011", "教材", "重要", "第 7 章 2D IR lineshapes（pp. 145–165）",
              "把线形理论直接落到 2D 峰形上。"),
            R("Hilborn1982", "综述", "重要", "全文",
              "Einstein 系数、截面、振子强度与偶极矩之间的换算一次讲清，单位陷阱都标出来了。"),
            R("Kubo1969", "里程碑论文", "延伸", "随机线形理论的主体部分",
              "运动变窄与 Kubo 线形的原始出处。"),
            R("Olivero1977", "里程碑论文", "延伸", "Voigt 线宽经验公式",
              "实际拟合吸收谱时常用的近似式。"),
        ],
        terms=[
            T("均匀展宽", "homogeneous broadening", "每个分子都具有的、由退相时间 T₂ 决定的线宽，线形为 Lorentz。"),
            T("非均匀展宽", "inhomogeneous broadening", "系综中跃迁频率的静态分布造成的线宽，线形近似 Gauss。"),
            T("谱扩散", "spectral diffusion", "单个分子的跃迁频率随时间在非均匀分布中游走的过程。"),
            T("频率涨落相关函数", "frequency–frequency correlation function (FFCF)", "C(t) = ⟨δω(t)δω(0)⟩，刻画频率涨落的幅度与记忆时间。"),
            T("振子强度", "oscillator strength", "无量纲的跃迁强度，正比于 |μ_eg|² 与跃迁频率之积。"),
        ],
    ),
    dict(
        id="F15", zh="泵浦–探测光谱", en="Pump–probe (transient absorption) spectroscopy", short="泵浦–探测",
        layer=5, prereqs=["F12", "F13"], chapters=[23], weeks=(14, 15), hours=16,
        why="PC-TWINS 本质上是在泵浦–探测装置上加一个 TWINS；先把普通瞬态吸收做熟，2DES 只是多一根激发频率轴。",
        checklist=[
            C("核心", "能由斩波测得的 T_on、T_off 计算 ΔT/T 与 ΔA = −log₁₀(T_on/T_off)，并说明二者的符号约定"),
            C("核心", "能把 GSB、SE、ESA 三种贡献与 ΔT/T 的正负一一对应"),
            C("核心", "能由每像素光电子数估算单发测量的散粒噪声极限 ΔT/T，并算出达到目标信噪比所需的平均次数"),
            C("熟悉", "能说明白光探测的啁啾使零时刻随波长变化，并会做群延迟（啁啾）校正"),
            C("熟悉", "能识别零时刻附近的相干伪信号（交叉相位调制、溶剂信号），并说明其来源"),
            C("熟悉", "能说明魔角（54.7°）偏振设置为何能消除转动扩散对布居动力学的影响"),
            C("了解", "知道全局分析与目标分析可以从数据中提取衰减相关谱与物种相关谱"),
        ],
        readings=[
            R("Berera2009", "综述", "首读", "全文，重点看原理与信号解读部分",
              "瞬态吸收的原理、信号符号与解读，写给入门者。"),
            R("Megerle2009", "里程碑论文", "重要", "啁啾校正、相干伪信号与溶剂贡献各节",
              "宽带瞬态吸收的实操规范，数据处理流程可直接照做。"),
            R("Lorenc2002", "里程碑论文", "重要", "零时刻伪信号的分类与模型",
              "辨认交叉相位调制等伪信号的经典参考。"),
            R("Kovalenko1999", "里程碑论文", "延伸", "啁啾超连续探测的理论处理",
              "需要定量理解啁啾探测带来的谱形畸变时再读。"),
        ],
        terms=[
            T("瞬态吸收", "transient absorption", "泵浦后测量探测光吸收随延迟变化的光谱方法，即泵浦–探测。"),
            T("差分透射", "differential transmission ΔT/T", "泵浦开与关时探测透射的相对变化。"),
            T("啁啾校正", "chirp correction", "按波长修正白光探测零时刻的数据处理步骤。"),
            T("交叉相位调制", "cross-phase modulation (XPM)", "泵浦在介质中引起的折射率变化调制探测光相位，产生零时刻伪信号。"),
            T("魔角", "magic angle", "泵浦与探测偏振夹角 54.7°，使信号不受取向弛豫影响。"),
        ],
    ),
    dict(
        id="F16", zh="二维电子光谱原理与读谱", en="2DES principles & reading 2D spectra", short="2DES 原理",
        layer=5, prereqs=["F13", "F14"], chapters=[0, 22, 24, 25], weeks=(15, 17), hours=30,
        why="这是整个领域的核心对象：知道两根频率轴从哪来、对角峰、交叉峰、峰形与量子拍各说明什么，才能判断实验结果是否可信。",
        checklist=[
            C("核心", "能说明 2D 谱的激发轴来自对相干时间 t₁ 的傅里叶变换，探测轴来自光谱仪色散（或对 t₃ 的变换）"),
            C("核心", "能由 rephasing 与 non-rephasing 谱相加得到吸收型 2D 谱，并说明单独的 rephasing 谱为何出现相位扭曲峰形"),
            C("核心", "能在耦合二聚体模型的 2D 谱上标出对角峰、交叉峰与 ESA 峰的位置，并说明各自来源"),
            C("熟悉", "能由峰的对角与反对角线宽读出非均匀与均匀展宽，并用中心线斜率随 t₂ 的变化估算谱扩散时间"),
            C("熟悉", "能说明等待时间内交叉峰增长、对角峰衰减对应能量转移"),
            C("熟悉", "能说明电子相干与振动相干在 2D 拍频图中的典型差异，并知道这一争论的代表性文献"),
            C("熟悉", "能说明 2D NMR 的间接维思想与 2DES 激发轴的对应关系"),
            C("了解", "知道 2DES 的几种实现几何（BOXCARS、泵浦–探测、全共线）及各自的优缺点"),
        ],
        readings=[
            R("Cundiff2013", "综述", "首读", "全文（6 页）",
              "先用一篇短文建立 2D 光谱的全景图，再读长综述。"),
            R("Jonas2003", "综述", "首读", "第 1–4 节：2D 谱的定义、相位与吸收型谱",
              "2DES 最常被引用的综述，定义与符号是领域标准。"),
            R("Hybl1998", "里程碑论文", "重要", "全文",
              "第一篇二维电子光谱实验，看清楚最初的动机与装置。"),
            R("Khalil2003", "里程碑论文", "重要", "全文（4 页）",
              "为什么要把 rephasing 与 non-rephasing 相加才得到吸收型峰形。"),
            R("Brixner2005", "里程碑论文", "延伸", "全文，重点看交叉峰随等待时间的演化",
              "用 2DES 直接看到光合复合物中的电子耦合与能量转移路径。"),
        ],
        terms=[
            T("激发频率 / 探测频率", "excitation / detection frequency", "2D 谱的两根轴，分别由 t₁ 与 t₃（或光谱仪）得到。"),
            T("吸收型 2D 谱", "absorptive 2D spectrum", "rephasing 与 non-rephasing 之和的实部，峰形不扭曲。"),
            T("交叉峰", "cross peak", "激发与探测频率不同的峰，表示两个跃迁之间存在耦合或能量转移。"),
            T("中心线斜率", "center-line slope (CLS)", "峰沿探测轴切片的极大值连线的斜率，近似正比于归一化 FFCF。"),
            T("量子拍", "quantum beat", "等待时间内相干态造成的信号振荡，频率等于两能级差。"),
            T("等待时间", "waiting / population time", "第二与第三次相互作用之间的时间 t₂（常记作 T）。"),
        ],
    ),
    dict(
        id="F17", zh="泵浦–探测几何 2DES 与探测链", en="Pump–probe-geometry 2DES & the detection chain", short="泵浦–探测 2DES",
        layer=6, prereqs=["F11", "F15", "F16"], chapters=[28, 29], weeks=(18, 20), hours=30,
        why="PC-TWINS 采用泵浦–探测几何：共线泵浦脉冲对加自外差探测；要搭建和调试，必须把相位、背景、探测器与噪声这条链路吃透。",
        checklist=[
            C("核心", "能说明泵浦–探测几何中信号沿探测方向发射并被探测光自外差，因此 rephasing 与 non-rephasing 同时记录、相加即得吸收型谱"),
            C("核心", "能写出数据处理流程：ΔT/T(t₁, T, λ) → 去除不随 t₁ 振荡的背景 → 对 t₁ 做 FT → 波长换算为频率 → 2D 谱"),
            C("核心", "能说明单个泵浦脉冲产生的普通泵浦–探测信号不随 t₁ 振荡，FT 后落在激发频率零点，并给出去除方法"),
            C("熟悉", "能说明信号与本振（探测光）天然相位锁定，因此不像 BOXCARS 那样需要事后相位校正"),
            C("熟悉", "能列出探测链各环节（光谱仪、线阵相机、斩波与逐发读出、参考通道）并估算各自的噪声贡献"),
            C("熟悉", "能说明泵浦散射光进入光谱仪会在 t₁ 的 FT 后沿对角线产生伪峰，以及斩波或相位循环如何抑制它"),
            C("了解", "知道 Shim 与 Zanni 用脉冲整形器在同一几何实现 2D 光谱与相位循环，可与 TWINS 方案对照"),
        ],
        readings=[
            R("Rehault2014", "里程碑论文", "首读", "全文：TWINS + 泵浦–探测几何 2DES 的装置、标定与数据处理",
              "你要搭的装置的直接前身，每一步都值得复现。"),
            R("Shim2009", "综述", "重要", "泵浦–探测几何的信号推导与相位循环各节",
              "说明如何把泵浦–探测装置改造成 2D 光谱仪，与 TWINS 方案对照阅读。"),
            R("Fuller2015", "综述", "重要", "各种实现几何的比较",
              "了解 TWINS 在所有 2DES 实现方案中的位置。"),
            R("Hamm2011", "教材", "重要", "第 9 章 Experimental designs, data collection and processing（pp. 176–216）",
              "实验设计、数据采集与处理的实用细节。"),
            R("Myers2008", "里程碑论文", "延伸", "泵浦–探测几何下的数据处理与相位处理各节",
              "后面 PC-TWINS 数据分离所沿用的处理流程就出自这篇。"),
        ],
        terms=[
            T("泵浦–探测几何", "pump–probe geometry", "两个泵浦脉冲共线、探测光同时充当第三束光与本振的 2DES 实现方式。"),
            T("自外差", "self-heterodyne", "信号与产生它的探测光沿同一方向传播并直接干涉检测。"),
            T("散射伪信号", "scatter artifact", "泵浦散射光与探测光或彼此干涉产生的、非样品响应的信号。"),
            T("线阵探测器", "line-scan / multichannel detector", "在光谱仪焦面逐发读出整条光谱的探测器，决定速度与噪声。"),
        ],
    ),
    dict(
        id="F18", zh="相位循环原理与方案设计", en="Phase cycling: principles & scheme design", short="相位循环",
        layer=6, prereqs=["F16"], chapters=[30, 31], weeks=(18, 20), hours=24,
        why="共线泵浦脉冲对的各条路径无法靠方向区分，只能靠相位：相位循环用离散傅里叶求和挑出目标路径，这就是 PC-TWINS 中“PC”的含义。",
        checklist=[
            C("核心", "能写出路径信号的相位因子 exp[i(αφ₁ + βφ₂)]，并说明不同路径由整数标签 (α, β) 区分"),
            C("核心", "能设计一个 N 步相位循环：选定相位序列与权重，证明离散傅里叶求和只保留目标 (α, β)"),
            C("核心", "能写出泵浦–探测几何中 rephasing、non-rephasing、零量子与双量子信号的相位标签，并据此判断最少需要几步循环"),
            C("熟悉", "能说明 NMR 中相干转移路径选择与光学相位循环之间的对应关系"),
            C("熟悉", "能说明 cogwheel 相位循环如何用较少的步数区分多条路径"),
            C("熟悉", "能估算相位步误差 δφ 导致的路径泄漏幅度（一阶约正比于 δφ）"),
            C("了解", "知道共线相位循环方案选择的一般理论（Tan 2008）"),
        ],
        readings=[
            R("Yan2009", "里程碑论文", "首读", "全文",
              "专门针对泵浦–探测几何的相位循环方案，与 PC-TWINS 最直接相关。"),
            R("Zhang2012", "里程碑论文", "重要", "全文",
              "泵浦–探测几何 2DES 相位循环方案的进一步设计。"),
            R("Tan2008", "里程碑论文", "重要", "相位循环选择原则各节",
              "给出共线多维光谱相位循环的一般规则。"),
            R("Bodenhausen1984", "里程碑论文", "延伸", "相干转移路径与相位循环的基本原理",
              "相位循环思想的 NMR 源头。"),
            R("Levitt2002", "里程碑论文", "延伸", "全文",
              "cogwheel 相位循环的原始论文。"),
        ],
        terms=[
            T("相位循环", "phase cycling", "改变各脉冲相位重复测量，再加权求和以挑出特定路径信号的方法。"),
            T("相干转移路径", "coherence-transfer pathway", "NMR 中对 Liouville 路径的称呼，以各时段的相干阶数标记。"),
            T("相位标签", "phase signature", "路径信号对各脉冲相位的依赖 exp[i(αφ₁ + βφ₂)] 中的整数 (α, β)。"),
            T("cogwheel 相位循环", "cogwheel phase cycling", "让各脉冲相位按不同步长同时变化，以少量步数分离多条路径。"),
            T("路径泄漏", "pathway leakage", "相位误差或步数不足使非目标路径残留在结果中。"),
        ],
    ),
    dict(
        id="F19", zh="PC-TWINS 信号链与因果复信号", en="PC-TWINS signal chain & causal complex signals", short="PC-TWINS 信号链",
        layer=7, prereqs=["F17", "F18"], chapters=[32, 33, 34], weeks=(21, 23), hours=36,
        why="这就是你的课题：Timmer 等在 TWINS 中加入消色差 λ/4 波片切换两脉冲的相对相位，从而分离 R、NR、零量子与双量子信号；要能逐式复现这篇论文。",
        checklist=[
            C("核心", "能用 Jones 演算推导 λ/4 波片方位为 45°、0°、90° 时两脉冲的相对相位 Δφ₀ = 0、−π/2、+π/2，以及第二偏振片转到 −45° 额外引入 π"),
            C("核心", "能写出 Δφ₀ = [0, π/2] 两步相位循环的数据组合方法，并说明它与探测时间上的因果性结合后如何分出 R 与 NR"),
            C("核心", "能说明对实数 ΔT 沿 t₁ 做 FT 会得到 ±ω₁ 两个镜像分量，以及施加因果性后如何得到可区分象限的复值信号"),
            C("核心", "能做一致性检验：把 R 谱沿 ω₁ = 0 翻转后与 NR 相加，应当重现吸收型 2D 谱"),
            C("熟悉", "能说明 PC-TWINS 只转动波片和偏振片而不移动楔片，因此不破坏延迟标定与共光路相位稳定性"),
            C("熟悉", "能用费曼图模拟有效三能级体系（激子 X 与双激子 XX）的 R 与 NR 谱，并解释 R 与 NR 振幅差来自非均匀展宽"),
            C("熟悉", "能说明波片色差与偏振片角度误差如何变成相位误差与干涉对比度下降，并能用线性自相关检验相位设置"),
            C("了解", "知道不做相位循环、仅靠因果性也能在泵浦–探测几何中分离部分信号（Timmer 2025）及其适用前提"),
        ],
        readings=[
            R("Timmer2024", "里程碑论文", "首读", "全文，重点：图 1 的波片与偏振片设置、图 2 的相位验证、图 3 的 R/NR 分离",
              "PC-TWINS 的原始论文，是你课题的出发点；先读 arXiv 版也可以。"),
            R("Timmer2024SI", "里程碑论文", "重要", "第 1 节 TWINS 的定量描述；第 4 节 R/NR 与 0Q/2Q 的数据处理",
              "正文略去的推导与数据处理细节都在补充材料里。"),
            R("Timmer2025", "里程碑论文", "重要", "全文",
              "同一组人展示仅用因果性分离信号的方法，可与相位循环方案对照。"),
            R("Myers2008", "里程碑论文", "重要", "数据处理各节",
              "Timmer 2024 分离 R/NR 时直接引用的处理流程。"),
        ],
        terms=[
            T("PC-TWINS", "phase-cycling TWINS", "在 TWINS 两偏振片之间加入消色差 λ/4 波片以控制两泵浦脉冲相对相位的方案。"),
            T("相对绝对相位", "relative absolute phase (Δφ₀)", "两泵浦脉冲载波–包络相位之差，与延迟无关、光谱上为常数。"),
            T("消色差 λ/4 波片", "achromatic quarter-wave plate", "在宽光谱范围内引入近似恒定 π/2 相位差的波片。"),
            T("复值信号", "complex-valued signal", "由相位循环或因果性得到的带正确符号频率的信号，可分出不同象限。"),
            T("因果性", "causality", "信号只能在最后一次光场作用之后出现，据此可约束时间或频率域数据。"),
        ],
    ),
    dict(
        id="F20", zh="零量子与双量子 2DES", en="Zero- & double-quantum 2DES", short="零/双量子 2DES",
        layer=8, prereqs=["F19"], chapters=[35], weeks=(24, 25), hours=14,
        why="双量子谱能直接看到双激发态与多体关联（如双激子），是 PC-TWINS 相比普通泵浦–探测 2DES 新增的能力，也是走向前沿应用的主要出口。",
        checklist=[
            C("核心", "能写出零量子与双量子信号的相位标签并画出对应费曼图，说明 2Q 谱在 ≈ ω_eg + ω_fe 处出峰"),
            C("核心", "能说明 Timmer 2024 中 0Q/2Q 测量采用反转的脉冲次序（T = 0、τ < 0，探测光与第二泵浦重合），以及为何要把激发轴平移为 ω_τ + ω_t"),
            C("熟悉", "能说明对无相互作用（谐性）体系两条双量子路径相互抵消，因而 2Q 信号直接反映多激子关联"),
            C("熟悉", "能说明 0Q 谱线宽反映布居弛豫、2Q 谱线宽反映双量子退相，并复述 Timmer 2024 在 J 聚集体上得到的时间量级"),
            C("熟悉", "能举出 2Q 2DES 研究半导体量子阱双激子的代表性实验"),
            C("了解", "知道高阶（如五阶）信号与激发强度依赖也能获取多激子信息，与 0Q/2Q 方法互补"),
        ],
        readings=[
            R("Kim2009", "综述", "首读", "全文",
              "双量子相干 2DES 的入门综述，讲清楚双量子路径与多体关联的关系。"),
            R("Cai2024", "里程碑论文", "重要", "泵浦–探测几何下 2Q 信号的采集次序与数据处理",
              "Timmer 2024 的 0Q/2Q 采集与处理方案即沿用此文。"),
            R("Stone2009", "里程碑论文", "重要", "全文，重点看双激子峰的分配",
              "2Q 2DES 在 GaAs 量子阱双激子上的标志性实验。"),
            R("Turner2010", "里程碑论文", "延伸", "全文",
              "把多量子 2D 光谱推向更高阶电子关联。"),
            R("Luttig2023", "综述", "延伸", "高阶信号的分类与提取方法",
              "了解高阶多维光谱与 0Q/2Q 方法的区别与互补。"),
        ],
        terms=[
            T("双量子相干", "double-quantum coherence", "基态与双激发态之间的相干 |f⟩⟨g|，频率约为两倍激发能。"),
            T("零量子", "zero-quantum", "相干阶数为零的路径（布居或激发态之间的相干），反映激发态动力学。"),
            T("双激子", "biexciton", "两个激子组成的束缚或关联态，其能量偏离两倍单激子能量。"),
            T("多体关联", "many-body correlation", "多个激发之间的相互作用，使体系响应偏离独立粒子之和。"),
        ],
    ),
    dict(
        id="F21", zh="标定、验收与伪信号", en="Calibration, acceptance tests & artefacts", short="标定与伪信号",
        layer=8, prereqs=["F19"], chapters=[36, 37], weeks=(24, 25), hours=22,
        why="新搭的谱仪必须先证明“它测到的是真的”：延迟轴、相位、背景与伪信号都要有可重复的标定方法与验收标准。",
        checklist=[
            C("核心", "能写出一套延迟轴标定流程（参考光谱 FT、楔片位置–延迟拟合、重复性统计）并给出量化的验收判据"),
            C("核心", "能用投影–切片关系做交叉检验：吸收型 2D 谱沿激发轴的投影应与同一等待时间的泵浦–探测谱一致"),
            C("核心", "能列出至少 5 种可伪装成信号的误差来源（泵浦散射、延迟非线性、相位步误差、激光漂移、高阶信号），并为每一种设计诊断实验"),
            C("熟悉", "能用激发强度依赖判断信号是否处于三阶微扰区"),
            C("熟悉", "能说明有限光束尺寸、光学厚样品与探测方式造成的传播效应如何扭曲 2D 峰形"),
            C("熟悉", "能说明准相位循环或斩波方案消除散射的原理"),
            C("了解", "知道相位同步欠采样可以大幅减少 t₁ 扫描点数"),
        ],
        readings=[
            R("Timmer2025", "里程碑论文", "首读", "各类信号贡献在泵浦–探测几何中的位置与分离",
              "知道每种贡献会出现在谱的哪里，是识别伪信号的前提。"),
            R("Yetzbacher2007", "里程碑论文", "重要", "传播、几何与探测造成峰形畸变的结论部分",
              "判断峰形异常是物理还是仪器造成的必读参考。"),
            R("Bloem2010", "里程碑论文", "重要", "准相位循环消除散射的方案",
              "在 2D IR 中验证过的散射抑制方法，可移植到 2DES。"),
            R("Krich2025", "里程碑论文", "延伸", "用强度变化分离响应阶数的方法",
              "定量检验信号是否混入高阶贡献。"),
            R("Bruder2018", "里程碑论文", "延伸", "相位同步欠采样原理",
              "缩短采集时间的一种思路。"),
        ],
        terms=[
            T("投影–切片定理", "projection-slice theorem", "2D 谱沿某轴的投影等于对应一维测量（如泵浦–探测谱）的关系，可用于检验与定相。"),
            T("验收测试", "acceptance test", "带有量化判据的一组标准测量，用于确认装置达到设计指标。"),
            T("强度依赖", "fluence dependence", "信号随激发能流的变化，三阶信号应与泵浦能流成正比。"),
            T("传播畸变", "propagation distortion", "光学厚样品中吸收与相位失配造成的峰形变化。"),
            T("准相位循环", "quasi-phase cycling", "利用斩波或调制在不精确控制相位时消除散射等背景的方案。"),
        ],
    ),
    dict(
        id="F22", zh="二维光谱数据分析", en="Analysis of 2D spectroscopy data", short="数据分析",
        layer=7, prereqs=["F17"], chapters=[38], weeks=(21, 23), hours=18,
        why="2DES 数据是 (ω₁, T, ω₃) 三维数组；全局分析、拍频分析与峰形分析把它压缩成可以写进论文的物理量。",
        checklist=[
            C("核心", "能对 2D 数据沿等待时间做全局多指数拟合，得到二维衰减相关谱（2D-DAS）"),
            C("核心", "能对拟合残差沿 T 做 FFT 得到拍频图，并在 ω₁–ω₃ 平面上定位某一拍频的振幅分布"),
            C("核心", "能计算 CLS 随 T 的衰减并拟合得到频率涨落相关函数的时间常数"),
            C("熟悉", "能用 SVD 或 PCA 估计数据中显著成分的个数，并用截断重构降噪"),
            C("熟悉", "能说明 DAS、EAS 与 SAS 的区别，以及目标分析需要哪些额外假设"),
            C("熟悉", "能给拟合参数报告不确定度（协方差矩阵或残差自助法）"),
            C("了解", "知道开源工具（如 pyglotaran）可以做全局与目标分析"),
        ],
        readings=[
            R("vanStokkum2004", "综述", "首读", "全局分析与目标分析的模型与参数估计各节",
              "全局 / 目标分析的标准参考，DAS、EAS、SAS 的定义都出自这里。"),
            R("Kwak2007", "里程碑论文", "重要", "CLS 方法的定义与适用条件",
              "从 2D 峰形提取 FFCF 的常用方法。"),
            R("Jolliffe2016", "综述", "重要", "第 1–2 节：PCA 的定义与计算",
              "SVD / PCA 的现代简明综述。"),
            R("Shlens2014", "讲义", "延伸", "全文",
              "从线性代数直觉出发的 PCA 教程，适合数学基础较弱时先读。"),
            R("Butkus2012", "里程碑论文", "延伸", "全文（4 页）",
              "拍频图中电子相干与振动相干的区分判据，做拍频分析前先读。"),
        ],
        terms=[
            T("全局分析", "global analysis", "用共享时间常数同时拟合所有波长（或所有 2D 像素）的数据。"),
            T("衰减相关谱", "decay-associated spectrum (DAS)", "全局多指数拟合中每个时间常数对应的振幅谱。"),
            T("拍频图", "beating map", "某一振荡频率的振幅在 ω₁–ω₃ 平面上的分布。"),
            T("奇异值分解", "singular value decomposition (SVD)", "把数据矩阵分解为正交成分与奇异值，用于判断成分数与降噪。"),
        ],
    ),
    dict(
        id="F23", zh="原理总串联、系统改进与研究前沿", en="Synthesis, instrument improvements & research frontier", short="前沿与改进",
        layer=9, prereqs=["F20", "F21", "F22"], chapters=[39, 40], weeks=(26, 26), hours=18,
        why="最后把光源、TWINS、样品、探测、相位循环与数据分析串成一条链，找出可以改进的环节，形成你自己的第一个研究问题。",
        checklist=[
            C("核心", "能画出 PC-TWINS 全信号链框图，并在每个环节标出决定最终信噪比与相位精度的参数"),
            C("核心", "能写出一页改进提案：指出当前装置的一个瓶颈（如采集速度、带宽或相位精度），给出量化目标与验证实验"),
            C("熟悉", "能比较作用量检测（荧光、光电流）2DES 与相干检测 2DES 在信号来源与相位循环要求上的差异"),
            C("熟悉", "能概述 2DES 在光合作用与半导体（如钙钛矿）中的代表性应用与尚未解决的问题"),
            C("熟悉", "能说明快速扫描方案提高采集效率的思路"),
            C("了解", "知道高阶多维光谱与强度依赖分离响应阶数是当前的活跃方向"),
        ],
        readings=[
            R("Biswas2022", "综述", "首读", "按与你样品相关的章节选读",
              "近年最全面的 2DES 综述，用来定位研究前沿与开放问题。"),
            R("Luttig2023", "综述", "重要", "全文",
              "高阶多维与泵浦–探测光谱的最新进展。"),
            R("Draeger2017", "里程碑论文", "延伸", "快速扫描方案与采集效率",
              "作用量检测与快速扫描的代表性实现。"),
            R("Richter2017", "里程碑论文", "延伸", "全文",
              "Cerullo 组用 2DES 研究钙钛矿载流子热化的例子。"),
        ],
        terms=[
            T("作用量检测", "action-detected spectroscopy", "通过荧光、光电流等非相干“作用”信号而非发射场来检测非线性响应。"),
            T("快速扫描", "rapid scan", "连续高速扫描延迟并同步采集以缩短测量时间的方案。"),
            T("信号链", "signal chain", "从光源到最终谱图的全部光学、电子学与数据处理环节。"),
            T("高阶响应", "higher-order response", "五阶及以上的非线性响应，携带多激发相互作用的信息。"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class DataError(Exception):
    pass


def item_key(module_id: str, item: dict) -> str:
    if item.get("key"):
        return f"{module_id}-{item['key']}"
    digest = hashlib.sha1(item["text"].encode("utf-8")).hexdigest()[:6]
    return f"{module_id}-{digest}"


def validate() -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    ids = [m["id"] for m in MODULES]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"重复的模块 ID: {sorted(dupes)}")
    by_id = {m["id"]: m for m in MODULES}

    if not 15 <= len(MODULES) <= 25:
        errors.append(f"模块数 {len(MODULES)} 不在 15–25 之间")

    weeks_total = PLAN["weeks"]
    load = [0.0] * (weeks_total + 1)
    all_keys: set[str] = set()
    chapters_seen: set[int] = set()
    used_refs: set[str] = set()

    for m in MODULES:
        mid = m["id"]
        for field in ("zh", "en", "short", "why"):
            if not m.get(field):
                errors.append(f"{mid}: 缺少字段 {field}")
        if not isinstance(m.get("layer"), int) or m["layer"] < 0:
            errors.append(f"{mid}: layer 必须是非负整数")
        for p in m["prereqs"]:
            if p not in by_id:
                errors.append(f"{mid}: 前置模块 {p} 不存在")
            elif by_id[p]["layer"] >= m["layer"]:
                errors.append(f"{mid}（第 {m['layer']} 层）: 前置 {p} 位于第 {by_id[p]['layer']} 层，必须严格更低")
        if len(set(m["prereqs"])) != len(m["prereqs"]):
            errors.append(f"{mid}: 前置模块重复")

        # checklist
        n = len(m["checklist"])
        if not 6 <= n <= 8:
            errors.append(f"{mid}: 掌握清单 {n} 条，应为 6–8 条")
        for it in m["checklist"]:
            if it["level"] not in LEVELS:
                errors.append(f"{mid}: 未知掌握层级 {it['level']!r}")
            text = it["text"]
            if not (text.startswith("能") or text.startswith("知道")):
                errors.append(f"{mid}: 清单条目须以“能…”或“知道…”开头，便于检查: {text}")
            if "理解" in text or "掌握" in text:
                errors.append(f"{mid}: 清单条目含不可检查的“理解/掌握”: {text}")
            k = item_key(mid, it)
            if k in all_keys:
                errors.append(f"{mid}: 清单条目键重复 {k}（文字重复？）")
            all_keys.add(k)
        if not any(it["level"] == "核心" for it in m["checklist"]):
            errors.append(f"{mid}: 至少需要一条“核心”条目")

        # readings
        n = len(m["readings"])
        if not 2 <= n <= 5:
            errors.append(f"{mid}: 推荐阅读 {n} 条，应为 2–5 条")
        if not any(r["priority"] == "首读" for r in m["readings"]):
            errors.append(f"{mid}: 缺少“首读”")
        seen = set()
        for r in m["readings"]:
            if r["ref"] not in REFS:
                errors.append(f"{mid}: 文献键 {r['ref']} 不在 REFS 中")
            if r["ref"] in seen:
                errors.append(f"{mid}: 文献 {r['ref']} 重复列出")
            seen.add(r["ref"])
            used_refs.add(r["ref"])
            if r["type"] not in READING_TYPES:
                errors.append(f"{mid}: 未知文献类型 {r['type']!r}")
            if r["priority"] not in PRIORITIES:
                errors.append(f"{mid}: 未知优先级 {r['priority']!r}")
            if not r["part"] or not r["why"]:
                errors.append(f"{mid}: 文献 {r['ref']} 缺少“读哪部分”或“为什么读”")

        # glossary
        n = len(m["terms"])
        if not 3 <= n <= 6:
            errors.append(f"{mid}: 术语 {n} 条，应为 3–6 条")
        for t in m["terms"]:
            if not (t["zh"] and t["en"] and t["definition"]):
                errors.append(f"{mid}: 术语字段不完整 {t}")

        # chapters
        for ch in m["chapters"]:
            if not 0 <= ch <= 40:
                errors.append(f"{mid}: 教材章节 {ch} 超出 0–40")
            chapters_seen.add(ch)

        # schedule
        a, b = m["weeks"]
        if not 1 <= a <= b <= weeks_total:
            errors.append(f"{mid}: 周次 {a}–{b} 不在 1–{weeks_total} 内")
        else:
            for w in range(a, b + 1):
                load[w] += m["hours"] / (b - a + 1)
        for p in m["prereqs"]:
            if p in by_id and by_id[p]["weeks"][1] >= a:
                errors.append(f"{mid}: 第 {a} 周开始，但前置 {p} 到第 {by_id[p]['weeks'][1]} 周才结束")

    # term uniqueness (zh) across modules
    zh_terms = [t["zh"] for m in MODULES for t in m["terms"]]
    dup_terms = {z for z in zh_terms if zh_terms.count(z) > 1}
    if dup_terms:
        errors.append(f"术语在多个模块中重复: {sorted(dup_terms)}")

    # acyclicity (Kahn) — redundant with the layer rule, but checked explicitly
    indeg = {m["id"]: 0 for m in MODULES}
    succ = defaultdict(list)
    for m in MODULES:
        for p in m["prereqs"]:
            if p in indeg:
                succ[p].append(m["id"])
                indeg[m["id"]] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    visited = 0
    while queue:
        n_ = queue.pop()
        visited += 1
        for s in succ[n_]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if visited != len(MODULES):
        errors.append("依赖图存在环")

    # weekly study load
    for w in range(1, weeks_total + 1):
        if not PLAN["hours_min"] - 1e-9 <= load[w] <= PLAN["hours_max"] + 1e-9:
            errors.append(f"第 {w} 周学习量 {load[w]:.1f} h，超出 {PLAN['hours_min']}–{PLAN['hours_max']} h")

    missing = sorted(set(range(41)) - chapters_seen)
    if missing:
        warnings.append(f"教材章节未被任何模块覆盖: {missing}")
    unused = sorted(set(REFS) - used_refs)
    if unused:
        warnings.append(f"REFS 中未被引用的条目: {unused}")
    for key, ref in REFS.items():
        if not (ref.get("doi") or ref.get("arxiv") or ref.get("url")):
            errors.append(f"文献 {key} 没有 DOI、arXiv 或 URL")

    if errors:
        raise DataError("\n".join(errors))
    return warnings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def build() -> dict:
    by_id = {m["id"]: m for m in MODULES}
    succ = defaultdict(list)
    for m in MODULES:
        for p in m["prereqs"]:
            succ[p].append(m["id"])
    refs_out = {}
    for key, r in REFS.items():
        links = []
        if r.get("doi"):
            links.append({"label": "DOI", "href": f"https://doi.org/{r['doi']}"})
        if r.get("arxiv"):
            links.append({"label": "arXiv", "href": f"https://arxiv.org/abs/{r['arxiv']}"})
        if r.get("url"):
            links.append({"label": "网页", "href": r["url"]})
        refs_out[key] = {
            "authors": r["authors"], "title": r["title"], "venue": r["venue"],
            "volume": r.get("volume", ""), "pages": r.get("pages", ""), "year": r["year"],
            "doi": r.get("doi", ""), "arxiv": r.get("arxiv", ""), "links": links,
            "verified": r.get("status", "verified") == "verified", "note": r.get("note", ""),
        }
    modules_out = []
    for m in MODULES:
        modules_out.append({
            "id": m["id"], "zh": m["zh"], "en": m["en"], "short": m["short"], "layer": m["layer"],
            "prereqs": m["prereqs"], "successors": succ[m["id"]], "why": m["why"],
            "chapters": m["chapters"], "weeks": list(m["weeks"]), "hours": m["hours"],
            "checklist": [{"key": item_key(m["id"], it), "level": it["level"], "text": it["text"]}
                          for it in m["checklist"]],
            "readings": [{k: r[k] for k in ("ref", "type", "priority", "part", "why")} for r in m["readings"]],
            "terms": m["terms"],
        })
    weeks = PLAN["weeks"]
    load = [0.0] * weeks
    for m in MODULES:
        a, b = m["weeks"]
        for w in range(a, b + 1):
            load[w - 1] += m["hours"] / (b - a + 1)
    return {
        "generated": date.today().isoformat(),
        "plan": dict(PLAN, weekly_load=[round(x, 1) for x in load],
                     total_hours=sum(m["hours"] for m in MODULES)),
        "levels": [{"name": n, "hint": LEVEL_HINT[n]} for n in LEVELS],
        "layers": {str(k): v for k, v in LAYER_NAMES.items()},
        "modules": modules_out,
        "refs": refs_out,
    }


def write(data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    OUT.write_text(
        "// Generated by gen_data.py — do not edit by hand.\n"
        f"window.KMAP_DATA = {payload};\n",
        encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Link checking
# ---------------------------------------------------------------------------
UA_API = "kmap-link-check/1.0 (https://lyz-623.github.io/knowledge-map/)"
UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def _get(url: str, headers: dict, tries: int = 5):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read(600_000)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (i + 1))
                last = e
                continue
            return e.code, b""
        except Exception as e:  # network errors
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(str(last))


def _norm(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "").lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _title_ok(ours: str, theirs: str) -> bool:
    a, b = _norm(re.sub(r"\(.*?\)", "", ours)), _norm(theirs)
    if not a or not b:
        return False
    k = min(len(a), len(b), 40)
    return a[:k] == b[:k] or a[:k] in b or b[:k] in a


def check_doi(doi: str, ref: dict) -> tuple[bool, str]:
    status, body = _get("https://api.crossref.org/works/" + urllib.parse.quote(doi), {"User-Agent": UA_API})
    source = "Crossref"
    if status == 200 and not (json.loads(body)["message"].get("title") or [""])[0]:
        status = 404  # Crossref stub without a title (e.g. figshare supplements): ask doi.org instead
    if status == 404:  # DataCite and other registration agencies: content negotiation at doi.org
        status, body = _get("https://doi.org/" + doi,
                            {"User-Agent": UA_API, "Accept": "application/vnd.citationstyles.csl+json"})
        source = "doi.org"
        if status != 200:
            return False, f"DOI 无法解析（Crossref 404，doi.org {status}）"
        m = json.loads(body)
        title = m.get("title", "")
        years = {(m.get("issued", {}).get("date-parts") or [[None]])[0][0]}
    elif status != 200:
        return False, f"Crossref HTTP {status}"
    else:
        m = json.loads(body)["message"]
        title = (m.get("title") or [""])[0]
        years = set()
        for k in ("issued", "published-print", "published-online", "published"):
            parts = (m.get(k, {}).get("date-parts") or [[None]])[0]
            if parts and parts[0]:
                years.add(parts[0])
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip()
    notes = []
    if not _title_ok(ref["title"], title):
        notes.append(f"标题不一致：{title[:80]!r}")
    if years and ref["year"] not in years and not any(abs(ref["year"] - y) <= 1 for y in years if y):
        notes.append(f"年份不一致：{sorted(y for y in years if y)}")
    if notes:
        return False, f"{source}: " + "；".join(notes)
    return True, f"{source} OK（{title[:60]}…）" if len(title) > 60 else f"{source} OK（{title}）"


def check_arxiv(aid: str, ref: dict) -> tuple[bool, str]:
    status, body = _get(f"https://export.arxiv.org/api/query?id_list={aid}", {"User-Agent": UA_API})
    if status != 200:
        return False, f"arXiv HTTP {status}"
    text = body.decode("utf-8", "replace")
    titles = re.findall(r"<title>(.*?)</title>", text, re.S)
    if len(titles) < 2:
        return False, "arXiv 未找到该编号"
    t = re.sub(r"\s+", " ", titles[1]).strip()
    if not _title_ok(ref["title"], t):
        return False, f"arXiv 标题不一致：{t[:80]!r}"
    return True, f"arXiv OK（{t[:60]}）"


def check_url(url: str, expect: str | None) -> tuple[bool, str]:
    status, body = _get(url, {"User-Agent": UA_WEB, "Accept-Language": "en"})
    if status != 200:
        return False, f"HTTP {status}"
    if expect and expect.lower() not in body.decode("utf-8", "replace").lower():
        return False, f"HTTP 200，但页面中找不到“{expect}”"
    return True, "HTTP 200" + (f"，含“{expect}”" if expect else "")


def check_links() -> int:
    print(f"检查 {len(REFS)} 条文献的链接（Crossref / doi.org / arXiv / 网页）…\n")
    failures = 0
    unverified = []
    for key, ref in REFS.items():
        results = []
        if ref.get("doi"):
            results.append(("DOI " + ref["doi"], *check_doi(ref["doi"], ref)))
            time.sleep(0.3)
        if ref.get("arxiv"):
            results.append(("arXiv " + ref["arxiv"], *check_arxiv(ref["arxiv"], ref)))
            time.sleep(0.5)
        if ref.get("url"):
            results.append(("URL", *check_url(ref.get("url_check", ref["url"]), ref.get("url_expect"))))
        for what, ok, msg in results:
            mark = "OK  " if ok else "FAIL"
            if not ok:
                failures += 1
            print(f"[{mark}] {key:<22} {what:<38} {msg}")
        if ref.get("status") == "unverified":
            unverified.append(key)
    print()
    print(f"共 {len(REFS)} 条文献，链接失败 {failures} 项。")
    if unverified:
        print("页面上标为“未能核实”的条目: " + ", ".join(unverified))
        for k in unverified:
            print(f"  - {k}: {REFS[k].get('note', '')}")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="只校验数据，不写 data.js")
    ap.add_argument("--check-links", action="store_true", help="校验后在线检查所有 DOI / arXiv / URL")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        warnings = validate()
    except DataError as e:
        print("数据校验失败：\n" + str(e), file=sys.stderr)
        return 2
    for w in warnings:
        print("警告: " + w)
    data = build()
    n_items = sum(len(m["checklist"]) for m in data["modules"])
    n_terms = sum(len(m["terms"]) for m in data["modules"])
    print(f"校验通过：{len(MODULES)} 个模块，{1 + max(m['layer'] for m in MODULES)} 层，"
          f"{n_items} 条清单，{len(REFS)} 条文献，{n_terms} 个术语，"
          f"总计 {data['plan']['total_hours']} h / {PLAN['weeks']} 周，"
          f"每周 {min(data['plan']['weekly_load'])}–{max(data['plan']['weekly_load'])} h。")
    if not args.check:
        write(data)
        print(f"已写入 {OUT.name}")
    if args.check_links:
        return check_links()
    return 0


if __name__ == "__main__":
    sys.exit(main())
