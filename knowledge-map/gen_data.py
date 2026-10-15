#!/usr/bin/env python3
"""Generate data.js for the PC-TWINS knowledge map.

All content (modules with their knowledge cards, readings and term cards)
lives in this file. Edit it, then run:

    python gen_data.py                # validate and write data.js
    python gen_data.py --check        # validate only, do not write
    python gen_data.py --check-links  # validate, then check every DOI / arXiv ID / URL online

Math is written in LaTeX: inline as $...$ in any text field, and as bare
LaTeX (no dollar signs) in the `tex` field of a key result. The page renders
it with KaTeX. Validation fails loudly (non-zero exit) if the dependency
graph has a cycle, a prerequisite is not in a strictly lower layer, a module
has the wrong number of concepts / results / readings / terms, a module has
no "首读" reading, an ID is duplicated, or math is not written as LaTeX
(unbalanced $ or braces, non-ASCII inside math, or math symbols such as
Greek letters, sub/superscript digits, "_" or "^" outside $...$).
"""

from __future__ import annotations

import argparse
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

SITE = {
    "title": "PC-TWINS 知识地图",
    "subtitle": "二维电子光谱与 PC-TWINS 的知识组织：按依赖分层的模块、知识卡片、经核实的文献与术语卡片。",
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


def F(name, tex, note=""):
    """One key result: a short name, the formula in LaTeX (no $), an optional one-line note."""
    return dict(name=name, tex=tex, note=note)


def T(zh, en, definition):
    """One term card."""
    return dict(zh=zh, en=en, definition=definition)


# ---------------------------------------------------------------------------
# Modules. Each module is a knowledge card:
#   why       one-sentence position of the module in the field
#   concepts  3-6 key concepts (short statements, inline math as $...$)
#   results   2-5 key results / formulas (F(name, tex, note))
#   readings  2-5 verified readings, at least one 首读
#   terms     3-6 term cards
# chapters = related chapters of the Chinese textbook (0-40, text only).
# ---------------------------------------------------------------------------
MODULES = [
    dict(
        id="F1", zh="复数、相量与线性代数", en="Complex numbers, phasors & linear algebra", short="复数与线性代数",
        layer=0, prereqs=[], chapters=[1, 2],
        why="光场、相位和量子态都用复数与矩阵书写，这是后面所有推导共用的语言。",
        concepts=[
            r"同频振荡可写成复数的实部：$A\cos(\omega t+\varphi)=\mathrm{Re}\,[A\,e^{i(\omega t+\varphi)}]$，同频振荡相加只需把复振幅相加。",
            r"两个复振幅相加后取模平方会出现交叉项，这就是光学干涉项的数学来源。",
            r"厄米矩阵（$A=A^\dagger$）的本征值为实数、本征向量正交，对应可观测量；幺正矩阵（$U^\dagger U=I$）保持内积，对应无损演化。",
            r"本征分解 $A=V\Lambda V^{-1}$ 把矩阵函数（如 $e^{-iHt/\hbar}$）化成对本征值的标量运算。",
            r"张量积 $\otimes$ 把两个子系统的态空间组合成复合系统的态空间。",
        ],
        results=[
            F("欧拉公式", r"e^{i\theta}=\cos\theta+i\sin\theta"),
            F("两相量叠加的模平方", r"\left|e^{i\alpha}+e^{i\beta}\right|^2=2+2\cos(\alpha-\beta)",
              r"第二项就是干涉项，只依赖相位差。"),
            F("本征方程", r"A\mathbf{v}=\lambda\mathbf{v},\qquad \det(A-\lambda I)=0"),
            F(r"$2\times 2$ 厄米矩阵的本征值",
              r"\begin{pmatrix}a&b\\ b^{*}&d\end{pmatrix}:\quad \lambda_\pm=\frac{a+d}{2}\pm\sqrt{\left(\frac{a-d}{2}\right)^{2}+|b|^{2}}",
              r"二能级体系的能级劈裂与 Rabi 频率都由它给出。"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", "第 3 章 Complex numbers and hyperbolic functions（pp. 83–114）；第 8 章 Matrices and vector spaces（pp. 241–315）中本征值、厄米与幺正矩阵各节",
              "从零讲起、例题密集，适合补基础。"),
            R("Boas2006", "教材", "重要", "第 3 章（线性代数：矩阵、线性向量空间与矩阵对角化）",
              "比 Riley 更口语化，作为同一内容的第二种讲法。"),
            R("MIT1806", "讲义", "延伸", "讲本征值、对角化与对称矩阵的几讲视频",
              "Strang 的课程以几何直觉见长。"),
        ],
        terms=[
            T("相量", "phasor", r"把同频振荡 $A\cos(\omega t+\varphi)$ 记作复数 $A e^{i\varphi}$，加法与求导变成复数运算。"),
            T("欧拉公式", "Euler's formula", r"$e^{i\theta}=\cos\theta+i\sin\theta$，连接复指数与三角函数。"),
            T("本征值", "eigenvalue", r"满足 $A\mathbf{v}=\lambda\mathbf{v}$ 的数 $\lambda$；对厄米算符而言就是可能的测量结果。"),
            T("厄米矩阵", "Hermitian matrix", r"等于自身共轭转置的矩阵（$A=A^\dagger$），本征值全为实数。"),
            T("幺正矩阵", "unitary matrix", r"满足 $U^\dagger U=I$ 的矩阵，保持内积与概率守恒，描述无损演化。"),
        ],
    ),
    dict(
        id="F2", zh="微积分、常微分方程与概率统计", en="Calculus, ODEs & probability", short="微积分与概率",
        layer=0, prereqs=[], chapters=[3],
        why="布居与相干的演化是一阶线性微分方程，噪声与误差棒靠概率统计，两者从 Bloch 方程一直用到数据分析。",
        concepts=[
            r"一阶线性方程 $\dot y=-y/T+f(t)$ 的解是指数衰减核与驱动项的卷积，所有唯象弛豫方程都是这种形式。",
            r"阻尼谐振子 $\ddot x+\gamma\dot x+\omega_0^2x=0$ 在欠阻尼时以 $\omega_d=\sqrt{\omega_0^2-\gamma^2/4}$ 振荡并以 $e^{-\gamma t/2}$ 衰减，是“响应函数”的经典原型。",
            r"独立同分布的 $N$ 次测量取平均后，均值的不确定度按 $1/\sqrt{N}$ 下降；前提是噪声互不相关。",
            r"光子与光电子计数服从泊松统计，方差等于均值，因此散粒噪声的相对涨落为 $1/\sqrt{N}$。",
            r"误差传递用一阶偏导把输入量的不确定度传到输出量；相关误差需要加协方差项。",
        ],
        results=[
            F("一阶线性方程的解", r"y(t)=y(0)\,e^{-t/T}+\int_0^{t}e^{-(t-t')/T}f(t')\,dt'"),
            F("均值的标准误", r"\sigma_{\bar x}=\frac{\sigma}{\sqrt{N}}"),
            F("泊松分布", r"P(n)=\frac{\bar n^{\,n}e^{-\bar n}}{n!},\qquad \mathrm{Var}(n)=\bar n"),
            F("误差传递（不相关输入）", r"\sigma_f^{2}\approx\sum_i\left(\frac{\partial f}{\partial x_i}\right)^{2}\sigma_{x_i}^{2}"),
            F("高斯积分与半高全宽", r"\int_{-\infty}^{\infty}e^{-ax^{2}}\,dx=\sqrt{\frac{\pi}{a}},\qquad \mathrm{FWHM}=2\sqrt{2\ln 2}\,\sigma"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", "第 14–15 章 First-order / Higher-order ODEs（pp. 468–530）；第 30–31 章 Probability, Statistics（pp. 1119–1304）中基本分布与误差各节",
              "一本书覆盖本模块全部数学；概率统计只读常用分布、期望方差与误差传递。"),
            R("Boas2006", "教材", "重要", r"第 8 章 Ordinary differential equations（第三版把 Laplace 变换与 $\delta$ 函数也放在这一章）",
              r"$\delta$ 函数与 Laplace 变换在讲冲击响应时会再用到。"),
            R("Tokmakoff2025", "讲义", "延伸", "第 6 章 Classical Description of Spectroscopy（6.2–6.4 受驱阻尼振子与冲击响应）",
              "用阻尼振子的语言提前引出“响应函数”。"),
        ],
        terms=[
            T("时间常数", "time constant", r"指数衰减 $e^{-t/T}$ 中的 $T$，信号降到 $1/e$ 所需的时间。"),
            T("标准误", "standard error of the mean", r"均值的不确定度 $\sigma/\sqrt{N}$，随平均次数增加而减小。"),
            T("散粒噪声", "shot noise", r"光子或电子到达的离散性造成的泊松噪声，相对涨落为 $1/\sqrt{N}$。"),
            T("误差传递", "error propagation", "由输入量的不确定度经一阶偏导估计输出量不确定度的方法。"),
        ],
    ),
    dict(
        id="F3", zh="傅里叶变换与离散采样", en="Fourier transform & discrete sampling", short="傅里叶与采样",
        layer=1, prereqs=["F1", "F2"], chapters=[4],
        why="2DES 的激发频率轴就是对延迟做傅里叶变换得到的；步长、扫描长度与窗函数决定谱的范围、分辨率与假峰。",
        concepts=[
            r"傅里叶变换把时间信号分解为频率分量；2DES 的激发轴来自对相干时间 $t_1$ 的变换。",
            r"卷积定理：时域相乘对应频域卷积。有限扫描等于乘一个矩形窗，谱线因此与 sinc 函数卷积；切趾窗以分辨率换取更低旁瓣。",
            r"以间隔 $\Delta t$ 采样会使频谱以 $1/\Delta t$ 为周期重复，高于 Nyquist 频率的成分折叠到低频（混叠）。",
            r"零填充只在频域插值；真实分辨率由最长延迟 $T_{\max}$ 决定。",
            r"因果信号（$t<0$ 时为零）的频谱实部与虚部由 Hilbert 变换互相决定，即 Kramers–Kronig 关系。",
        ],
        results=[
            F("傅里叶变换（本站约定）", r"\tilde f(\omega)=\int_{-\infty}^{\infty}f(t)\,e^{i\omega t}\,dt,\qquad f(t)=\frac{1}{2\pi}\int_{-\infty}^{\infty}\tilde f(\omega)\,e^{-i\omega t}\,d\omega",
              "符号与归一化约定因书而异，读文献时先确认约定。"),
            F("卷积定理", r"\mathcal{F}[f*g]=\mathcal{F}[f]\cdot\mathcal{F}[g]"),
            F("高斯脉冲的时间带宽积", r"\Delta t\,\Delta\nu=\frac{2\ln 2}{\pi}\approx 0.441", "$\\Delta t$、$\\Delta\\nu$ 均为强度的半高全宽。"),
            F("采样定理与分辨率", r"\Delta t\le\frac{1}{2\nu_{\max}},\qquad \delta\nu\approx\frac{1}{T_{\max}}"),
        ],
        readings=[
            R("Riley2006", "教材", "首读", r"第 13 章 Integral transforms（pp. 433–467）：Fourier 变换、$\delta$ 函数、卷积定理与 Parseval 定理",
              "把连续傅里叶变换的定义与常用定理一次学全。"),
            R("GriffithsdeHaseth2007", "教材", "重要", "第 3 章 Sampling the Interferogram（pp. 57–74）；第 4 章 Fourier Transforms（pp. 75–95）",
              "FTIR 与 TWINS 激发轴同为“对干涉图采样再做 FT”，Nyquist、混叠与切趾的实际处理讲得最实用。"),
            R("Hamm2011", "教材", "延伸", "附录 Fourier transformation（pp. 254–259）",
              "多维光谱语境下的 FT 约定与离散 FT 要点。"),
        ],
        terms=[
            T("时间带宽积", "time–bandwidth product", "脉冲时域宽度与频域宽度之积，存在由脉冲形状决定的下限。"),
            T("奈奎斯特频率", "Nyquist frequency", r"采样率的一半 $1/(2\Delta t)$；高于它的频率成分会被折叠到低频。"),
            T("混叠", "aliasing", "采样不足时高频信号被错误地映射到低频位置的现象。"),
            T("切趾", "apodization", "对有限长数据乘窗函数以压低截断带来的旁瓣，代价是峰变宽。"),
            T("零填充", "zero padding", "在时域数据后补零以加密频率采样点，不增加信息量。"),
            T("卷积定理", "convolution theorem", "时域卷积对应频域相乘，反之亦然。"),
        ],
    ),
    dict(
        id="F4", zh="电磁波、偏振与双折射", en="EM waves, polarization & birefringence", short="偏振与双折射",
        layer=1, prereqs=["F1"], chapters=[5, 6, 7],
        why="TWINS 的核心是双折射楔片：o 光与 e 光的群速度差产生可控延迟，偏振投影决定相位；Jones 演算是读懂 PC-TWINS 的工具。",
        concepts=[
            r"介质中的平面波 $E=E_0e^{i(kz-\omega t)}$ 满足 $k=n\omega/c$；探测器测到的是时间平均光强。",
            r"完全偏振光用二维复 Jones 矢量描述，偏振元件是 $2\times 2$ 矩阵，光依次通过多个元件时按顺序从右向左相乘。",
            r"单轴晶体把入射光分解为 o 光与 e 光，二者折射率不同，于是获得不同的相位与群延迟。",
            r"相位延迟由相折射率 $n$ 决定，脉冲包络的延迟由群折射率 $n_g$ 决定；TWINS 产生的是两偏振分量之间的群延迟差。",
            r"两块光轴互相垂直的双折射晶体的延迟相减，因此可以得到连续可调、能够过零的相对延迟。",
            r"$\alpha$-BBO 为中心对称结构、没有二阶非线性，用作双折射元件；$\beta$-BBO 无中心对称，用于倍频。",
        ],
        results=[
            F("光强", r"I=\tfrac12\,c\,n\,\varepsilon_0\,|E_0|^{2}"),
            F("波片与旋转后的 Jones 矩阵",
              r"W(\Gamma)=\begin{pmatrix}1&0\\ 0&e^{i\Gamma}\end{pmatrix},\qquad J(\theta)=R(\theta)\,J_0\,R(-\theta)",
              r"快轴沿 $x$；$\lambda/4$ 波片 $\Gamma=\pi/2$，$\lambda/2$ 波片 $\Gamma=\pi$；$R(\theta)$ 为把矢量转过 $\theta$ 的旋转矩阵。"),
            F("o/e 光的相位差", r"\Delta\varphi=\frac{2\pi}{\lambda}\,(n_e-n_o)\,L"),
            F("群延迟差与群折射率", r"\Delta\tau=\frac{L}{c}\,\left(n_{g,e}-n_{g,o}\right),\qquad n_g=n-\lambda\frac{dn}{d\lambda}"),
        ],
        readings=[
            R("Saleh1991", "教材", "首读", "第 6 章 Polarization and Crystal Optics（pp. 193–237）：Jones 矩阵、波片、单轴晶体",
              "偏振与晶体光学一章讲透，直接对应 TWINS 需要的全部工具。"),
            R("Griffiths2017", "教材", "重要", "第 9 章 Electromagnetic Waves（pp. 382–435）",
              "从 Maxwell 方程到平面波、能流与介质中传播的标准推导。"),
            R("Jones1941", "里程碑论文", "延伸", "第 I 部分：Jones 演算的定义与讨论",
              "Jones 演算的原始论文。"),
            R("Malitson1965", "里程碑论文", "延伸", "熔融石英的 Sellmeier 色散公式与系数表",
              "计算群折射率与 GDD 时最常用的材料数据来源。"),
        ],
        terms=[
            T("Jones 矩阵", "Jones matrix", r"作用在二维复偏振矢量上的 $2\times 2$ 矩阵，描述偏振元件对完全偏振光的作用。"),
            T("双折射", "birefringence", "折射率随偏振方向不同的性质，使两个正交偏振分量获得不同的相位与群延迟。"),
            T("寻常光 / 非常光", "ordinary / extraordinary ray", "单轴晶体中偏振垂直于 / 处在光轴与波矢所成平面内的两个本征偏振分量。"),
            T("群折射率", "group index", r"$n_g=n-\lambda\,dn/d\lambda$，决定脉冲包络的传播速度 $c/n_g$。"),
            T("波片", "wave plate", r"利用双折射在两正交偏振间引入固定相位差（如 $\pi$ 或 $\pi/2$）的元件。"),
        ],
    ),
    dict(
        id="F5", zh="量子力学基础与二能级体系", en="Quantum mechanics basics & two-level systems", short="二能级量子体系",
        layer=1, prereqs=["F1", "F2"], chapters=[15],
        why="2DES 把电子跃迁抽象为二能级或三能级体系；跃迁偶极、叠加态与 Rabi 振荡是所有响应函数的出发点。",
        concepts=[
            r"态矢量 $|\psi\rangle$ 按含时薛定谔方程演化；能量本征态只累积相位 $e^{-iE_nt/\hbar}$。",
            r"叠加态中两个本征态的相对相位以跃迁频率 $\omega_{eg}=(E_e-E_g)/\hbar$ 旋转，偶极期望值随之振荡，这就是光学相干。",
            r"偶极近似下光与分子的耦合为 $-\hat\mu\cdot\mathbf{E}(t)$，强弱由跃迁偶极 $\mu_{eg}=\langle e|\hat\mu|g\rangle$ 决定。",
            r"旋转波近似：近共振、且 $|\Omega|$ 与失谐都远小于 $\omega_{eg}$ 时，丢掉以约 $2\omega$ 振荡的反共振项。",
            r"弱场极限下激发布居正比于场强平方；2DES 的三阶信号就是在这一微扰区间定义的。",
        ],
        results=[
            F("含时薛定谔方程", r"i\hbar\,\frac{\partial}{\partial t}|\psi(t)\rangle=\hat H\,|\psi(t)\rangle"),
            F("叠加态的自由演化", r"|\psi(t)\rangle=c_g\,e^{-iE_gt/\hbar}|g\rangle+c_e\,e^{-iE_et/\hbar}|e\rangle"),
            F("Rabi 振荡（旋转波近似）",
              r"P_e(t)=\frac{\Omega^{2}}{\Omega^{2}+\Delta^{2}}\,\sin^{2}\!\left(\frac{\sqrt{\Omega^{2}+\Delta^{2}}\;t}{2}\right),\qquad \Omega=\frac{\mu_{eg}E_0}{\hbar}",
              r"共振（$\Delta=0$）时 $P_e=\sin^2(\Omega t/2)$。"),
        ],
        readings=[
            R("Griffiths2018", "教材", "首读", "第 3 章 Formalism（pp. 91–130）；第 11 章 Quantum Dynamics（pp. 402–445）中二能级体系与含时微扰各节",
              "Dirac 记号与二能级动力学的入门标准读物。"),
            R("Tokmakoff2025", "讲义", "重要", "第 2 章 2.3 Two-Level System；第 3 章 3.4 Resonant Driving of a Two-Level System 与 3.5 The Interaction Picture",
              "面向光谱学的写法，为相互作用绘景与响应函数铺路。"),
        ],
        terms=[
            T("二能级体系", "two-level system", r"只保留基态 $|g\rangle$ 与激发态 $|e\rangle$ 的最简量子模型。"),
            T("跃迁偶极矩", "transition dipole moment", r"$\mu_{eg}=\langle e|\hat\mu|g\rangle$，决定跃迁与光耦合的强弱和偏振取向。"),
            T("Rabi 频率", "Rabi frequency", r"$\Omega=\mu_{eg}E_0/\hbar$，共振驱动下布居在两能级间往返的角频率。"),
            T("旋转波近似", "rotating-wave approximation", r"忽略以约 $2\omega$ 快速振荡的反共振项的近似。"),
            T("叠加态", "superposition state", r"$c_g|g\rangle+c_e|e\rangle$ 形式的态，其相对相位携带相干信息。"),
        ],
    ),
    dict(
        id="F6", zh="干涉、相干性与外差探测", en="Interference, coherence & heterodyne detection", short="干涉与外差",
        layer=2, prereqs=["F3", "F4"], chapters=[8],
        why="探测器只能测强度，2DES 的相位信息全靠信号场与参考场（本振）的干涉项读出。",
        concepts=[
            r"探测器只响应 $|E|^2$；相位只能通过两束场叠加时的交叉项读出。",
            r"相干时间约为光谱宽度的倒数；程差超过相干长度后条纹消失。",
            r"Wiener–Khinchin 定理：场的自相关与功率谱互为傅里叶变换，因此干涉图的傅里叶变换就是光谱（傅里叶变换光谱学）。",
            r"外差探测用强本振放大弱信号的交叉项并保留其相位；在泵浦–探测几何中，探测光本身就是本振。",
            r"相位稳定性：程差抖动 $\delta L$ 造成相位误差 $2\pi\,\delta L/\lambda$；在 600 nm 处，$\lambda/100$ 只对应 6 nm。",
            r"当本振散粒噪声占主导时，继续增大本振功率不再提高外差信噪比。",
        ],
        results=[
            F("双光束干涉", r"I=I_1+I_2+2\sqrt{I_1I_2}\,|\gamma_{12}|\cos\Delta\varphi", r"$|\gamma_{12}|$ 为复相干度的模。"),
            F("条纹可见度", r"V=\frac{I_{\max}-I_{\min}}{I_{\max}+I_{\min}}"),
            F("外差交叉项", r"|E_{\mathrm{LO}}+E_s|^{2}-|E_{\mathrm{LO}}|^{2}\approx 2\,\mathrm{Re}\left[E_{\mathrm{LO}}^{*}E_s\right]", r"$|E_s|\ll|E_{\mathrm{LO}}|$。"),
            F("Wiener–Khinchin 定理与相干时间", r"S(\omega)\propto\int_{-\infty}^{\infty}\langle E^{*}(t)\,E(t+\tau)\rangle\,e^{i\omega\tau}\,d\tau,\qquad \tau_c\approx\frac{1}{\Delta\nu}"),
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
            T("条纹可见度", "fringe visibility", r"$V=(I_{\max}-I_{\min})/(I_{\max}+I_{\min})$，衡量干涉对比度与相干程度。"),
            T("相干时间", "coherence time", r"光场保持确定相位关系的时间尺度 $\tau_c\approx 1/\Delta\nu$。"),
            T("外差探测", "heterodyne detection", "让弱信号与强参考场干涉，通过交叉项测量信号的振幅与相位。"),
            T("本振", "local oscillator", "外差探测中作为相位参考的强场；泵浦–探测几何中由探测光担任。"),
            T("干涉图", "interferogram", "探测强度随延迟变化的曲线，其傅里叶变换给出光谱。"),
        ],
    ),
    dict(
        id="F7", zh="超短脉冲：时频描述、色散与啁啾", en="Ultrashort pulses: time–frequency picture, dispersion & chirp", short="超短脉冲与色散",
        layer=2, prereqs=["F3", "F4"], chapters=[10, 11],
        why="2DES 的时间分辨率与带宽来自飞秒脉冲；光路中每一块玻璃（包括 TWINS 楔片）都会引入色散。",
        concepts=[
            r"脉冲由光谱振幅与光谱相位共同决定；光谱相位平坦（或线性）时得到变换极限的最短脉冲。",
            r"光谱相位的各阶：$\varphi_0$ 是载波–包络相位，只在两个脉冲干涉时可见；$\varphi_1$ 是群延迟，只平移脉冲；$\varphi_2$（GDD）带来线性啁啾与展宽；$\varphi_3$（TOD）带来不对称拖尾。",
            r"正常色散材料给出正 GDD（红光在前）；棱镜对、光栅对与啁啾镜提供负 GDD 进行补偿。",
            r"自相位调制在无色散时只展宽光谱而不改变脉宽，是白光产生与脉冲压缩的物理基础。",
        ],
        results=[
            F("光谱相位展开", r"\varphi(\omega)=\varphi_0+\varphi_1(\omega-\omega_0)+\frac{\varphi_2}{2}(\omega-\omega_0)^{2}+\frac{\varphi_3}{6}(\omega-\omega_0)^{3}+\cdots"),
            F("群延迟", r"\tau_g(\omega)=\frac{d\varphi}{d\omega}"),
            F("高斯脉冲经 GDD 后的脉宽", r"\tau_{\mathrm{out}}=\tau_{\mathrm{in}}\sqrt{1+\left(\frac{4\ln 2\;\varphi_2}{\tau_{\mathrm{in}}^{2}}\right)^{2}}",
              r"$\tau$ 为强度半高全宽，输入为变换极限。"),
            F("材料的 GDD", r"\varphi_2=\mathrm{GVD}\cdot L,\qquad \mathrm{GVD}=\frac{\lambda^{3}}{2\pi c^{2}}\,\frac{d^{2}n}{d\lambda^{2}}"),
        ],
        readings=[
            R("Weiner2009", "教材", "首读", "第 1 章 Introduction and Review（pp. 1–31）；第 4 章 Dispersion and Dispersion Compensation（pp. 147–197）",
              "脉冲的时频描述与色散补偿最系统的现代教材。"),
            R("Diels2006", "教材", "重要", "第 1 章 Fundamentals（pp. 1–60）；第 2 章 Femtosecond Optics（pp. 61–142）",
              "相位展开与色散元件的另一种讲法，推导更细。"),
            R("Kartner2005", "讲义", "延伸", "讲义第 2–3 章（色散、非线性脉冲传播与脉冲压缩）",
              "免费讲义，可与教材对照。"),
            R("Fork1984", "里程碑论文", "延伸", "全文（3 页）",
              "棱镜对负色散的原始论文。"),
        ],
        terms=[
            T("变换极限", "transform limit", "给定光谱下可能的最短脉冲，对应平坦（线性）光谱相位。"),
            T("群延迟色散", "group-delay dispersion (GDD)", r"光谱相位对频率的二阶导数 $\varphi_2$，单位 $\mathrm{fs}^2$，导致脉冲展宽与啁啾。"),
            T("群速度色散", "group-velocity dispersion (GVD)", r"单位长度材料的 GDD，单位 $\mathrm{fs}^2/\mathrm{mm}$。"),
            T("啁啾", "chirp", "脉冲瞬时频率随时间变化的现象，正啁啾时红光在前。"),
            T("载波–包络相位", "carrier–envelope phase (CEP)", r"载波峰值相对包络峰值的相位，即光谱相位的常数项 $\varphi_0$。"),
        ],
    ),
    dict(
        id="F8", zh="密度矩阵、相干与系综", en="Density matrix, coherence & ensembles", short="密度矩阵",
        layer=2, prereqs=["F5"], chapters=[16],
        why="溶液和固体样品都是系综，必须用密度矩阵描述：对角元是布居、非对角元是相干，2DES 的每条信号路径都是密度矩阵元之间的跳转。",
        concepts=[
            r"系综用 $\rho=\sum_i p_i|\psi_i\rangle\langle\psi_i|$ 描述：对角元 $\rho_{nn}$ 是布居，非对角元 $\rho_{nm}$ 是相干。",
            r"纯态满足 $\mathrm{Tr}\,\rho^{2}=1$，混合态 $\mathrm{Tr}\,\rho^{2}<1$；室温下光学跃迁满足 $\hbar\omega\gg k_BT$，热平衡系综几乎全部处于基态。",
            r"宏观极化是系综平均偶极，只有相干元对它有贡献。",
            r"$T_1$ 描述布居弛豫，$T_2$ 描述单个分子的相干衰减；系综频率分布带来的额外退相不是单分子性质，可以被光子回波重聚。",
            r"Lindblad 形式是保证 $\rho$ 始终正定的一般马尔可夫弛豫方程。",
        ],
        results=[
            F("Liouville–von Neumann 方程", r"\frac{d\rho}{dt}=-\frac{i}{\hbar}\,[\hat H,\rho]"),
            F("相干元的自由演化（唯象退相）", r"\rho_{eg}(t)=\rho_{eg}(0)\,e^{-i\omega_{eg}t}\,e^{-t/T_2}"),
            F("退相时间", r"\frac{1}{T_2}=\frac{1}{2T_1}+\frac{1}{T_2^{*}}",
              r"$T_2^{*}$ 此处表示纯退相时间；各书记号不同，NMR 中 $T_2^{*}$ 常指含非均匀展宽的表观时间。"),
            F("宏观极化", r"P(t)=N\,\mathrm{Tr}\left[\hat\mu\,\rho(t)\right]=N\left(\mu_{ge}\,\rho_{eg}(t)+\mathrm{c.c.}\right)"),
        ],
        readings=[
            R("Tokmakoff2025", "讲义", "首读", "第 12 章 12.4 Mixed States、12.5 The Density Matrix、12.6 Time-Dependence of the Density Matrix",
              "为光谱学写的密度矩阵入门，符号与响应函数一致。"),
            R("Boyd2020", "教材", "重要", "第 3 章 Quantum-Mechanical Theory of the Nonlinear Optical Susceptibility（pp. 137–202）中密度矩阵表述各节",
              "用密度矩阵加唯象弛豫计算极化率，直接连到响应理论。"),
            R("Lindblad1976", "里程碑论文", "延伸", "引言与主定理的形式",
              "Lindblad 形式的出处；数学证明可以跳过。"),
        ],
        terms=[
            T("密度矩阵", "density matrix", r"$\rho=\sum_i p_i|\psi_i\rangle\langle\psi_i|$，描述系综（含混合态）的完整量子态。"),
            T("布居", "population", r"密度矩阵对角元 $\rho_{nn}$，处于能级 $n$ 的概率。"),
            T("相干", "coherence", r"密度矩阵非对角元 $\rho_{nm}$，以 $\omega_{nm}$ 振荡，是辐射与量子拍的来源。"),
            T("光学 Bloch 方程", "optical Bloch equations", r"含 $T_1$、$T_2$ 唯象弛豫的二能级密度矩阵运动方程。"),
            T("退相", "dephasing", "相干元因涨落或系综平均而衰减、但布居不变的过程。"),
        ],
    ),
    dict(
        id="F9", zh="非线性光学与脉冲诊断", en="Nonlinear optics & pulse characterisation", short="非线性光学与诊断",
        layer=3, prereqs=["F7"], chapters=[12, 13],
        why="不测脉冲就不知道样品处的时间分辨率；SHG 自相关与 FROG 是调光路的日常工具，也是理解 NOPA 的物理基础。",
        concepts=[
            r"强场下极化按场的幂次展开；二阶过程（SHG、SFG、参量放大）只发生在非中心对称晶体中。",
            r"二阶过程需要相位匹配才能相干累积；相位匹配带宽约与晶体长度成反比，所以宽带脉冲要用薄晶体。",
            r"强度自相关只给出脉宽（还要假设脉冲形状），不含光谱相位；FROG 记录随延迟变化的谱图，再迭代恢复振幅与相位。",
            r"SHG-FROG 对时间反演不敏感，无法单独确定啁啾符号。",
            r"在样品位置测得的泵浦–探测互相关给出仪器响应函数与零时刻。",
        ],
        results=[
            F("极化的幂级数展开", r"P=\varepsilon_0\left(\chi^{(1)}E+\chi^{(2)}E^{2}+\chi^{(3)}E^{3}+\cdots\right)"),
            F("频率关系与相位匹配", r"\omega_3=\omega_1+\omega_2,\qquad \Delta k=k_3-k_1-k_2=0", r"SHG 是 $\omega_1=\omega_2$ 的特例。"),
            F("强度自相关", r"A(\tau)=\int_{-\infty}^{\infty}I(t)\,I(t-\tau)\,dt,\qquad \tau_{\mathrm{AC}}=\sqrt{2}\,\tau_p\ \ (\text{Gaussian})"),
            F("SHG-FROG 谱图", r"I_{\mathrm{FROG}}(\omega,\tau)=\left|\int_{-\infty}^{\infty}E(t)\,E(t-\tau)\,e^{i\omega t}\,dt\right|^{2}"),
        ],
        readings=[
            R("Trebino1997", "综述", "首读", "前半部分：自相关的局限、FROG 原理与各种几何",
              "FROG 发明者写的综述，是脉冲测量的标准入口。"),
            R("Weiner2009", "教材", "重要", "第 3 章 Ultrafast-Pulse Measurement Methods（pp. 85–146）；第 5 章 Ultrafast Nonlinear Optics: Second Order（pp. 198–257）",
              "把脉冲测量与二阶非线性放在同一套符号下讲。"),
            R("Boyd2020", "教材", "重要", "第 1 章 The Nonlinear Optical Susceptibility（pp. 1–64）；第 2 章 Wave-Equation Description（pp. 65–135）中 SHG 与相位匹配各节",
              "非线性极化与相位匹配的标准推导。"),
            R("Trebino2000", "教材", "延伸", "实验装置与相位恢复算法各章",
              "动手搭 FROG 或写恢复程序时查阅。"),
        ],
        terms=[
            T("二次谐波", "second-harmonic generation (SHG)", r"$\chi^{(2)}$ 介质中两个 $\omega$ 光子合成一个 $2\omega$ 光子的过程。"),
            T("相位匹配", "phase matching", r"使各频率分量波矢满足 $\Delta k=0$，从而让非线性信号相干累积。"),
            T("强度自相关", "intensity autocorrelation", "脉冲与自身延迟副本的 SHG 信号随延迟的变化，只含脉宽信息。"),
            T("频率分辨光学开关", "FROG", "记录随延迟变化的非线性信号光谱（谱图），再迭代恢复脉冲振幅与相位。"),
            T("仪器响应函数", "instrument response function (IRF)", "泵浦与探测脉冲的互相关，限制可分辨的最快动力学。"),
        ],
    ),
    dict(
        id="F10", zh="微扰理论与非线性响应函数", en="Perturbation theory & nonlinear response functions", short="响应函数",
        layer=3, prereqs=["F3", "F8"], chapters=[17, 18],
        why=r"2DES 信号就是三阶极化 $P^{(3)}$；响应函数把“三个脉冲加等待时间”翻译成可计算的公式。",
        concepts=[
            r"在相互作用绘景中把密度矩阵按场的阶数展开，第 $n$ 阶修正含 $n$ 个与偶极算符的嵌套对易子。",
            r"线性响应函数的傅里叶变换是复极化率 $\chi^{(1)}(\omega)$：虚部对应吸收，实部对应色散。",
            r"三阶极化是响应函数与三个电场的三重卷积；$t_1$ 为相干时间，$t_2$ 为等待时间，$t_3$ 为探测时间。",
            r"$S^{(3)}$ 由 4 对 Liouville 路径及其复共轭组成，共 8 项；冲击极限下信号直接正比于响应函数。",
            r"因果性 $\theta(t)$ 使响应函数的实部与虚部满足 Kramers–Kronig 关系。",
            r"电偶极近似下各向同性介质的偶数阶响应为零，因此溶液中最低阶的非线性信号是三阶。",
        ],
        results=[
            F("线性响应", r"P^{(1)}(t)=\int_0^{\infty}S^{(1)}(t_1)\,E(t-t_1)\,dt_1,\qquad S^{(1)}(t)=\frac{i}{\hbar}\,\theta(t)\,\mathrm{Tr}\left\{[\hat\mu(t),\hat\mu(0)]\,\rho_{\mathrm{eq}}\right\}"),
            F("三阶极化", r"\begin{aligned}P^{(3)}(t)=\int_0^{\infty}\!\!dt_3\int_0^{\infty}\!\!dt_2\int_0^{\infty}\!\!dt_1\;&S^{(3)}(t_3,t_2,t_1)\\ &\times E(t-t_3)\,E(t-t_3-t_2)\,E(t-t_3-t_2-t_1)\end{aligned}"),
            F("三阶响应函数", r"S^{(3)}(t_3,t_2,t_1)=\left(\frac{i}{\hbar}\right)^{3}\theta(t_1)\,\theta(t_2)\,\theta(t_3)\sum_{\alpha=1}^{4}\left[R_\alpha-R_\alpha^{*}\right]"),
        ],
        readings=[
            R("Hamm2011", "教材", "首读", "第 3 章 Mukamelian or perturbative expansion of the density matrix（pp. 48–60）",
              "13 页讲清从密度矩阵到三阶响应函数，是最短的正确入口。"),
            R("Tokmakoff2025", "讲义", "重要", "第 14 章 Linear Response Theory（14.4 Quantum Linear Response Functions、14.5 Nonlinear response functions）",
              "从经典阻尼振子推广到量子响应函数，推导步步可跟。"),
            R("Mukamel2000", "综述", "延伸", "前两节：响应函数框架与多维相关光谱的分类",
              "该领域通用的理论语言与符号来源。"),
            R("Mukamel1995", "教材", "延伸", "非线性响应函数与 Liouville 空间路径的相关章节",
              "领域经典专著，作为查阅用；难度高。"),
        ],
        terms=[
            T("相互作用绘景", "interaction picture", "把已知的无微扰演化吸收进算符，只追踪由微扰引起的变化的表象。"),
            T("响应函数", "response function", "把各阶极化与入射电场联系起来的时间核，包含体系的全部动力学。"),
            T("三阶极化", "third-order polarization", r"$P^{(3)}$，与电场三次方成正比的宏观极化，是泵浦–探测与 2DES 信号的来源。"),
            T("冲击极限", "impulsive limit", r"把脉冲近似为 $\delta$ 函数的极限，此时信号直接正比于响应函数。"),
            T("极化率", "susceptibility", r"$\chi^{(n)}(\omega)$，响应函数在频域的表示。"),
        ],
    ),
    dict(
        id="F11", zh="谱干涉与 TWINS 双折射干涉仪", en="Spectral interferometry & the TWINS interferometer", short="谱干涉与 TWINS",
        layer=3, prereqs=["F6", "F7"], chapters=[26, 27],
        why="TWINS 用双折射楔片产生相位锁定的泵浦脉冲对，是 PC-TWINS 的心脏；延迟标定依靠谱干涉与傅里叶变换光谱技巧。",
        concepts=[
            r"TWINS 由偏振片、固定的双折射块和一对可平移的双折射楔片组成：入射光在 $45^\circ$ 偏振下分成两个正交分量，平移楔片改变有效厚度，从而连续调节并可过零的相对延迟，末端偏振片把两个分量投影到同一偏振。",
            r"共光路：两个脉冲走同一路径、只靠偏振区分，机械振动与空气扰动对二者几乎相同，因此相对延迟与相位天然稳定。",
            r"延迟来自两偏振分量的群延迟差，近似正比于楔片位置；双折射色散使相位延迟随波长变化，需要逐波长标定。",
            r"标定用傅里叶变换光谱法：记录线性干涉图对楔片位置的依赖，结合已知光谱求出位置与延迟的换算关系。",
            r"谱干涉：两个延迟脉冲在光谱仪上形成间隔 $2\pi/\tau$ 的条纹，傅里叶变换谱干涉（FTSI）可以提取二者的相位差。",
        ],
        results=[
            F("楔片有效厚度", r"\Delta L=\Delta x\,\tan\alpha", r"$\alpha$ 为楔角，$\Delta x$ 为横向平移量。"),
            F("TWINS 延迟（近似）", r"\tau(x)\approx\frac{n_{g,e}-n_{g,o}}{c}\,\bigl[L_B(x)-L_A\bigr]", r"$L_A$、$L_B$ 为光轴互相垂直的两部分材料的厚度。"),
            F("谱干涉", r"S(\omega)=|E_1(\omega)|^{2}+|E_2(\omega)|^{2}+2\,|E_1(\omega)E_2(\omega)|\cos\left[\omega\tau+\Delta\varphi(\omega)\right]"),
            F("线性干涉图（FT 光谱）", r"I(\tau)\propto\int_0^{\infty}S(\omega)\,\left[1+\cos(\omega\tau)\right]\,d\omega"),
        ],
        readings=[
            R("Brida2012", "里程碑论文", "首读", "全文（3 页）",
              "TWINS 用于二维光谱的原始方案：相位锁定脉冲对如何产生。"),
            R("Lepetit1995", "里程碑论文", "首读", "第 2–3 节：谱干涉原理与 FTSI 相位提取算法",
              "延迟与相位标定所用谱干涉方法的标准参考。"),
            R("Oriana2016", "里程碑论文", "重要", "装置设计与延迟标定各节",
              "楔片 FT 光谱仪的标定流程与 TWINS 相同。"),
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
        layer=4, prereqs=["F9"], chapters=[9, 14],
        why="2DES 的泵浦与探测通常来自 NOPA 与白光；光斑、聚焦、重叠与激发密度决定实验是否处于可解释的区间。",
        concepts=[
            r"锁模使激光腔各纵模保持固定相位关系，从而输出脉冲串；钛宝石振荡器常用 Kerr 透镜锁模。",
            r"啁啾脉冲放大（CPA）先展宽、再放大、最后压缩，以避免高峰值功率损伤增益介质。",
            r"光参量放大中一个泵浦光子分裂为信号光子与闲频光子；非共线几何让闲频光群速度在信号方向的投影等于信号光群速度，从而获得超宽带增益（NOPA）。",
            r"白光超连续产生有阈值行为；介质（蓝宝石、YAG、$\mathrm{CaF_2}$ 等）决定光谱范围与稳定性。",
            r"高斯光束的束腰与瑞利长度决定光斑与重叠体积；由脉冲能量与光斑估算的能流决定样品是否处于微扰区。",
        ],
        results=[
            F("参量过程的守恒关系", r"\omega_p=\omega_s+\omega_i,\qquad \mathbf{k}_p=\mathbf{k}_s+\mathbf{k}_i"),
            F("NOPA 宽带条件", r"v_{g,s}=v_{g,i}\cos\Omega", r"$\Omega$ 为信号光与闲频光的夹角。"),
            F("高斯光束", r"w(z)=w_0\sqrt{1+\left(\frac{z}{z_R}\right)^{2}},\qquad z_R=\frac{\pi w_0^{2}}{\lambda},\qquad w_0\approx\frac{\lambda f}{\pi w_{\mathrm{in}}}"),
            F("高斯光斑的峰值能流", r"F_{\mathrm{peak}}=\frac{2E_p}{\pi w_0^{2}}", r"$w_0$ 为 $1/e^{2}$ 强度半径。"),
        ],
        readings=[
            R("Cerullo2003", "综述", "首读", "OPA 原理与非共线相位匹配各节",
              "NOPA 原理与设计的标准综述。"),
            R("Manzoni2016", "综述", "重要", "全文",
              "以教学方式整理的 OPA 设计准则，比 2003 年综述更易读。"),
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
            T("瑞利长度", "Rayleigh range", r"高斯光束光斑面积增大一倍所对应的传播距离 $z_R=\pi w_0^2/\lambda$。"),
            T("锁模", "mode-locking", "使激光腔各纵模保持固定相位关系从而输出超短脉冲串的技术。"),
        ],
    ),
    dict(
        id="F13", zh="Liouville 路径与双边费曼图", en="Liouville pathways & double-sided Feynman diagrams", short="双边费曼图",
        layer=4, prereqs=["F10"], chapters=[19],
        why="双边费曼图是 2DES 的“语法”：每个峰、每种相位循环挑出的信号都对应若干张图，PC-TWINS 论文的核心论证都用图写成。",
        concepts=[
            r"双边费曼图左线代表 ket、右线代表 bra，时间自下而上；每个箭头是一次光场作用，最后一次作用后体系回到布居态并发射信号。",
            r"每个箭头贡献 $\pm\mathbf{k}_j$ 与 $\pm\varphi_j$，符号由箭头方向决定；信号波矢与相位是各贡献之和。",
            r"三阶信号分为基态漂白（GSB）、受激发射（SE）与激发态吸收（ESA）三类；ESA 的符号与前两类相反。",
            r"rephasing 路径在 $t_1$ 与 $t_3$ 期间相位反向旋转，可抵消非均匀退相（光子回波）；non-rephasing 路径同向旋转。",
            r"等待时间内处于相干态的路径产生量子拍；双量子路径中体系在两次作用后处于 $|f\rangle\langle g|$ 相干，以约 $\omega_{fg}$ 演化。",
            r"固定时间顺序的图只在脉冲不重叠时成立；脉冲重叠时还要考虑时序交换的路径。",
        ],
        results=[
            F("相位匹配方向", r"\mathbf{k}_{R}=-\mathbf{k}_1+\mathbf{k}_2+\mathbf{k}_3,\qquad \mathbf{k}_{NR}=+\mathbf{k}_1-\mathbf{k}_2+\mathbf{k}_3,\qquad \mathbf{k}_{2Q}=+\mathbf{k}_1+\mathbf{k}_2-\mathbf{k}_3"),
            F("一条 rephasing 路径（二能级，唯象退相）", r"R(t_3,t_2,t_1)\propto|\mu_{eg}|^{4}\,e^{+i\omega_{eg}t_1}\,e^{-i\omega_{eg}t_3}\,e^{-(t_1+t_3)/T_2}",
              r"$t_1$ 与 $t_3$ 的相位符号相反，这就是“重相位”的来源。"),
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
            T("激发态吸收", "excited-state absorption (ESA)", "激发态向更高能级吸收探测光产生的信号，符号与 GSB、SE 相反。"),
            T("重相位 / 非重相位", "rephasing / non-rephasing", r"$t_1$ 与 $t_3$ 期间相干的相位旋转方向相反 / 相同的两类路径。"),
        ],
    ),
    dict(
        id="F14", zh="弛豫、线形与线性吸收", en="Relaxation, lineshapes & linear absorption", short="弛豫与线形",
        layer=4, prereqs=["F10"], chapters=[20, 21],
        why="2D 峰形的对角与反对角宽度分别对应非均匀与均匀展宽，谱扩散让峰形随等待时间变圆；线形是从 2D 谱读出动力学的钥匙。",
        concepts=[
            r"均匀展宽来自每个分子都有的退相时间 $T_2$，给出 Lorentz 线形。",
            r"非均匀展宽来自系综中跃迁频率的静态分布，给出近似 Gauss 线形；在 2D 谱中表现为沿对角线拉长。",
            r"谱扩散：单个分子的频率随时间在分布中游走，用频率涨落相关函数描述；Kubo 模型中快调制导致运动变窄，慢调制趋于非均匀极限。",
            r"Voigt 线形是 Lorentz 与 Gauss 的卷积。",
            r"吸光度、摩尔吸光系数、振子强度、跃迁偶极与 Einstein 系数之间可以相互换算。",
            r"振动结构（Franck–Condon 进程、Huang–Rhys 因子）会在吸收谱上产生振动边带。",
        ],
        results=[
            F("Lorentz 线形", r"L(\omega)\propto\frac{\Gamma}{(\omega-\omega_0)^{2}+\Gamma^{2}},\qquad \Gamma=\frac{1}{T_2}", r"角频率下的半高全宽为 $2\Gamma$。"),
            F("Kubo 模型与运动变窄", r"C(t)=\langle\delta\omega(t)\,\delta\omega(0)\rangle=\Delta^{2}e^{-t/\tau_c};\qquad \Delta\tau_c\ll 1\;\Rightarrow\;\frac{1}{T_2^{*}}=\Delta^{2}\tau_c"),
            F("Beer–Lambert 定律", r"A=-\log_{10}\frac{I}{I_0}=\varepsilon\,c\,\ell"),
            F("振子强度（SI，取向平均）", r"f=\frac{2m_e\,\omega_{eg}}{3\hbar e^{2}}\,|\mu_{eg}|^{2}"),
            F("Voigt 线宽经验式", r"f_V\approx 0.5346\,f_L+\sqrt{0.2166\,f_L^{2}+f_G^{2}}", r"$f_L$、$f_G$、$f_V$ 分别为 Lorentz、Gauss、Voigt 线形的半高全宽。"),
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
              "拟合吸收谱时常用的近似式。"),
        ],
        terms=[
            T("均匀展宽", "homogeneous broadening", r"每个分子都具有的、由退相时间 $T_2$ 决定的线宽，线形为 Lorentz。"),
            T("非均匀展宽", "inhomogeneous broadening", "系综中跃迁频率的静态分布造成的线宽，线形近似 Gauss。"),
            T("谱扩散", "spectral diffusion", "单个分子的跃迁频率随时间在非均匀分布中游走的过程。"),
            T("频率涨落相关函数", "frequency–frequency correlation function (FFCF)", r"$C(t)=\langle\delta\omega(t)\,\delta\omega(0)\rangle$，刻画频率涨落的幅度与记忆时间。"),
            T("振子强度", "oscillator strength", r"无量纲的跃迁强度，正比于 $\omega_{eg}|\mu_{eg}|^2$。"),
        ],
    ),
    dict(
        id="F15", zh="泵浦–探测光谱", en="Pump–probe (transient absorption) spectroscopy", short="泵浦–探测",
        layer=5, prereqs=["F12", "F13"], chapters=[23],
        why="PC-TWINS 本质上是在泵浦–探测装置上加一个 TWINS；2DES 相对瞬态吸收只是多了一根激发频率轴。",
        concepts=[
            r"基态漂白与受激发射使探测透射增加（$\Delta T/T>0$），激发态吸收使其减少（$\Delta T/T<0$）。",
            r"斩波泵浦并逐发比较开、关两种状态，可以抵消激光的慢漂移。",
            r"白光探测光带有啁啾，零时刻随波长变化，需要做群延迟（啁啾）校正。",
            r"零时刻附近存在交叉相位调制、溶剂信号等相干伪信号，不是样品的布居响应。",
            r"泵浦与探测偏振成魔角时，信号不受转动扩散影响，只反映布居动力学。",
            r"全局与目标分析用共享时间常数同时拟合全部波长，得到衰减相关谱与物种相关谱。",
        ],
        results=[
            F("差分透射与差分吸光度", r"\frac{\Delta T}{T}=\frac{T_{\mathrm{on}}-T_{\mathrm{off}}}{T_{\mathrm{off}}},\qquad \Delta A=-\log_{10}\frac{T_{\mathrm{on}}}{T_{\mathrm{off}}}\approx-\frac{1}{\ln 10}\,\frac{\Delta T}{T}"),
            F("单对开/关测量的散粒噪声极限", r"\sigma_{\Delta T/T}\approx\sqrt{\frac{2}{N_e}}", r"$N_e$ 为每个像素每发的光电子数。"),
            F("魔角与各向同性信号", r"\theta_m=\arccos\frac{1}{\sqrt3}\approx 54.7^\circ,\qquad S_{\mathrm{iso}}=\frac{S_\parallel+2S_\perp}{3}"),
        ],
        readings=[
            R("Berera2009", "综述", "首读", "全文，重点看原理与信号解读部分",
              "瞬态吸收的原理、信号符号与解读，写给入门者。"),
            R("Megerle2009", "里程碑论文", "重要", "啁啾校正、相干伪信号与溶剂贡献各节",
              "宽带瞬态吸收的实操规范。"),
            R("Lorenc2002", "里程碑论文", "重要", "零时刻伪信号的分类与模型",
              "辨认交叉相位调制等伪信号的经典参考。"),
            R("Kovalenko1999", "里程碑论文", "延伸", "啁啾超连续探测的理论处理",
              "定量理解啁啾探测带来的谱形畸变。"),
        ],
        terms=[
            T("瞬态吸收", "transient absorption", "泵浦后测量探测光吸收随延迟变化的光谱方法，即泵浦–探测。"),
            T("差分透射", "differential transmission", r"$\Delta T/T$，泵浦开与关时探测透射的相对变化。"),
            T("啁啾校正", "chirp correction", "按波长修正白光探测零时刻的数据处理步骤。"),
            T("交叉相位调制", "cross-phase modulation (XPM)", "泵浦在介质中引起的折射率变化调制探测光相位，产生零时刻伪信号。"),
            T("魔角", "magic angle", r"泵浦与探测偏振夹角 $54.7^\circ$，使信号不受取向弛豫影响。"),
        ],
    ),
    dict(
        id="F16", zh="二维电子光谱原理与读谱", en="2DES principles & reading 2D spectra", short="2DES 原理",
        layer=5, prereqs=["F13", "F14"], chapters=[0, 22, 24, 25],
        why="这是整个领域的核心对象：两根频率轴从哪来，对角峰、交叉峰、峰形与量子拍各说明什么。",
        concepts=[
            r"激发轴来自对相干时间 $t_1$（泵浦脉冲对延迟）的傅里叶变换；探测轴来自光谱仪色散，等价于对 $t_3$ 的变换。",
            r"单独的 rephasing 或 non-rephasing 谱有相位扭曲的峰形；二者相加取实部得到吸收型 2D 谱。",
            r"对角峰对应单个跃迁，交叉峰表示两个跃迁之间存在耦合或能量转移，ESA 峰符号相反。",
            r"峰沿对角线的宽度反映非均匀展宽，沿反对角线的宽度反映均匀展宽；中心线斜率随 $t_2$ 衰减反映谱扩散。",
            r"交叉峰随 $t_2$ 增长对应能量转移；随 $t_2$ 振荡对应量子拍，可能来自电子相干或振动相干。",
            r"2DES 的激发轴借用了 2D NMR 的间接维思想；实现几何有 BOXCARS、泵浦–探测与全共线三类。",
        ],
        results=[
            F("2D 谱的定义", r"S_{2D}(\omega_1,t_2,\omega_3)=\int_0^{\infty}\!\!\int_0^{\infty}S(t_1,t_2,t_3)\,e^{i\omega_1t_1}\,e^{i\omega_3t_3}\,dt_1\,dt_3",
              "符号约定因文献而异：rephasing 信号在此约定下出现在负激发频率一侧。"),
            F("吸收型谱", r"S_{\mathrm{abs}}(\omega_1,\omega_3)=\mathrm{Re}\left[S_{R}(-\omega_1,\omega_3)+S_{NR}(\omega_1,\omega_3)\right]"),
            F("中心线斜率与频率涨落相关函数", r"\mathrm{CLS}(t_2)\approx\frac{C(t_2)}{C(0)}"),
        ],
        readings=[
            R("Cundiff2013", "综述", "首读", "全文（6 页）",
              "先用一篇短文建立 2D 光谱的全景图，再读长综述。"),
            R("Jonas2003", "综述", "首读", "第 1–4 节：2D 谱的定义、相位与吸收型谱",
              "2DES 最常被引用的综述，定义与符号是领域标准。"),
            R("Hybl1998", "里程碑论文", "重要", "全文",
              "第一篇二维电子光谱实验。"),
            R("Khalil2003", "里程碑论文", "重要", "全文（4 页）",
              "为什么要把 rephasing 与 non-rephasing 相加才得到吸收型峰形。"),
            R("Brixner2005", "里程碑论文", "延伸", "全文，重点看交叉峰随等待时间的演化",
              "用 2DES 直接看到光合复合物中的电子耦合与能量转移路径。"),
        ],
        terms=[
            T("激发频率 / 探测频率", "excitation / detection frequency", r"2D 谱的两根轴，分别由 $t_1$ 与 $t_3$（或光谱仪）得到。"),
            T("吸收型 2D 谱", "absorptive 2D spectrum", "rephasing 与 non-rephasing 之和的实部，峰形不扭曲。"),
            T("交叉峰", "cross peak", "激发与探测频率不同的峰，表示两个跃迁之间存在耦合或能量转移。"),
            T("中心线斜率", "center-line slope (CLS)", "峰沿探测轴切片的极大值连线的斜率，近似等于归一化的频率涨落相关函数。"),
            T("量子拍", "quantum beat", "等待时间内相干态造成的信号振荡，频率等于两能级差。"),
            T("等待时间", "waiting / population time", r"第二与第三次相互作用之间的时间 $t_2$（常记作 $T$）。"),
        ],
    ),
    dict(
        id="F17", zh="泵浦–探测几何 2DES 与探测链", en="Pump–probe-geometry 2DES & the detection chain", short="泵浦–探测 2DES",
        layer=6, prereqs=["F11", "F15", "F16"], chapters=[28, 29],
        why="PC-TWINS 采用泵浦–探测几何：共线泵浦脉冲对加自外差探测；相位、背景、探测器与噪声组成了这条信号链。",
        concepts=[
            r"共线泵浦对（$\mathbf{k}_1=\mathbf{k}_2$）与探测光 $\mathbf{k}_3$：rephasing 与 non-rephasing 信号都沿探测方向发射并被探测光自外差，因此同时被记录，直接给出吸收型谱。",
            r"信号与本振（探测光）天然相位锁定，不像 BOXCARS 几何那样需要事后定相。",
            r"单个泵浦脉冲产生的普通泵浦–探测信号不随 $t_1$ 振荡，傅里叶变换后落在 $\omega_1=0$，可扣除或滤掉。",
            r"泵浦散射光进入光谱仪，其光谱干涉随 $t_1$ 振荡，在 2D 谱上沿对角线形成伪峰；斩波或相位循环可以抑制它。",
            r"数据流程：$\Delta T/T(t_1,T,\lambda)$ → 去除不随 $t_1$ 振荡的背景 → 沿 $t_1$ 傅里叶变换 → 波长换算为频率 → 2D 谱。",
            r"探测链包括光谱仪、线阵相机、逐发读出与参考通道，各环节都进入噪声预算。",
        ],
        results=[
            F("信号方向", r"\pm\mathbf{k}_1\mp\mathbf{k}_2+\mathbf{k}_3=\mathbf{k}_3\qquad(\mathbf{k}_1=\mathbf{k}_2)"),
            F("散射光的光谱干涉", r"\left|E_1(\omega)+E_2(\omega)\right|^{2}=2\,|E(\omega)|^{2}\left[1+\cos(\omega t_1)\right]",
              r"两个相同脉冲；该项在 $\omega_1=\omega_3$ 处出峰，即沿对角线。"),
            F("波长到频率的换算", r"S(\omega)=S(\lambda)\,\frac{\lambda^{2}}{2\pi c}"),
        ],
        readings=[
            R("Rehault2014", "里程碑论文", "首读", "全文：TWINS + 泵浦–探测几何 2DES 的装置、标定与数据处理",
              "PC-TWINS 装置的直接前身。"),
            R("Shim2009", "综述", "重要", "泵浦–探测几何的信号推导与相位循环各节",
              "如何把泵浦–探测装置改造成 2D 光谱仪，可与 TWINS 方案对照。"),
            R("Fuller2015", "综述", "重要", "各种实现几何的比较",
              "TWINS 在所有 2DES 实现方案中的位置。"),
            R("Hamm2011", "教材", "重要", "第 9 章 Experimental designs, data collection and processing（pp. 176–216）",
              "实验设计、数据采集与处理的实用细节。"),
            R("Myers2008", "里程碑论文", "延伸", "泵浦–探测几何下的数据处理与相位处理各节",
              "PC-TWINS 数据分离所沿用的处理流程出自这篇。"),
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
        layer=6, prereqs=["F16"], chapters=[30, 31],
        why="共线泵浦脉冲对的各条路径无法靠方向区分，只能靠相位：相位循环用离散傅里叶求和挑出目标路径，这就是 PC-TWINS 中“PC”的含义。",
        concepts=[
            r"每条路径的信号以 $e^{i(\alpha\varphi_1+\beta\varphi_2)}$ 依赖各脉冲相位，整数标签 $(\alpha,\beta)$ 由对应费曼图的箭头方向决定。",
            r"在泵浦–探测几何中（探测光既作用又作本振，其相位相消），信号只依赖 $\Delta\varphi=\varphi_2-\varphi_1$：rephasing $\propto e^{+i\Delta\varphi}$，non-rephasing $\propto e^{-i\Delta\varphi}$，普通泵浦–探测项与 $\Delta\varphi$ 无关。",
            r"$N$ 步相位循环加权重求和等价于离散傅里叶滤波器：只有标签满足选择条件的路径留下。",
            r"NMR 中的相干转移路径选择是光学相位循环的源头；cogwheel 循环让各脉冲以不同步长同时变相，以较少步数分离多条路径。",
            r"相位步不准会使非目标路径泄漏到结果中，泄漏幅度一阶正比于相位误差。",
        ],
        results=[
            F("路径的相位依赖", r"S_{\alpha\beta}(\varphi_1,\varphi_2)=S_{\alpha\beta}\,e^{i(\alpha\varphi_1+\beta\varphi_2)}"),
            F("离散傅里叶滤波", r"S_{\alpha\beta}=\frac{1}{N}\sum_{m=0}^{N-1}S\bigl(\varphi^{(m)}\bigr)\,e^{-i\left(\alpha\varphi_1^{(m)}+\beta\varphi_2^{(m)}\right)}"),
            F(r"选择条件（相位步 $2\pi/N$）", r"\frac{1}{N}\sum_{m=0}^{N-1}e^{\,i(\ell-\ell')\,2\pi m/N}=\begin{cases}1,&\ell\equiv\ell'\pmod N\\ 0,&\text{otherwise}\end{cases}"),
            F("相位误差造成的泄漏", r"\frac{|S_{\mathrm{leak}}|}{|S|}\approx\delta\varphi", r"一阶近似，$\delta\varphi$ 为相位步误差（弧度）。"),
        ],
        readings=[
            R("Yan2009", "里程碑论文", "首读", "全文",
              "专门针对泵浦–探测几何的相位循环方案，与 PC-TWINS 最直接相关。"),
            R("Zhang2012", "里程碑论文", "重要", "全文",
              "泵浦–探测几何 2DES 相位循环方案的进一步设计。"),
            R("Tan2008", "里程碑论文", "重要", "相位循环选择原则各节",
              "共线多维光谱相位循环的一般规则。"),
            R("Bodenhausen1984", "里程碑论文", "延伸", "相干转移路径与相位循环的基本原理",
              "相位循环思想的 NMR 源头。"),
            R("Levitt2002", "里程碑论文", "延伸", "全文",
              "cogwheel 相位循环的原始论文。"),
        ],
        terms=[
            T("相位循环", "phase cycling", "改变各脉冲相位重复测量，再加权求和以挑出特定路径信号的方法。"),
            T("相干转移路径", "coherence-transfer pathway", "NMR 中对 Liouville 路径的称呼，以各时段的相干阶数标记。"),
            T("相位标签", "phase signature", r"路径信号对各脉冲相位依赖 $e^{i(\alpha\varphi_1+\beta\varphi_2)}$ 中的整数 $(\alpha,\beta)$。"),
            T("cogwheel 相位循环", "cogwheel phase cycling", "让各脉冲相位按不同步长同时变化，以少量步数分离多条路径。"),
            T("路径泄漏", "pathway leakage", "相位误差或步数不足使非目标路径残留在结果中。"),
        ],
    ),
    dict(
        id="F19", zh="PC-TWINS 信号链与因果复信号", en="PC-TWINS signal chain & causal complex signals", short="PC-TWINS 信号链",
        layer=7, prereqs=["F17", "F18"], chapters=[32, 33, 34],
        why=r"Timmer 等在 TWINS 的两个偏振片之间加入消色差 $\lambda/4$ 波片，切换两泵浦脉冲的相对相位而不移动楔片，从而分离 rephasing、non-rephasing、零量子与双量子信号。",
        concepts=[
            r"消色差 $\lambda/4$ 波片改变两泵浦脉冲的相对绝对相位 $\Delta\varphi_0$（在光谱上为常数），不移动楔片，因此不破坏延迟标定与共光路稳定性。",
            r"波片快轴在 $45^\circ$、$0^\circ$、$90^\circ$ 时 $\Delta\varphi_0=0$、$-\pi/2$、$+\pi/2$；第二偏振片从 $+45^\circ$ 转到 $-45^\circ$ 再额外引入 $\pi$（Timmer 2024，图 1）。",
            r"两步循环 $\Delta\varphi_0\in\{0,\pi/2\}$ 结合探测时间上的因果性，把 rephasing 与 non-rephasing 分到不同的谱象限，再线性组合得到分离谱（沿用 Myers 等 2008 年的处理）。",
            r"一致性检验：rephasing 谱沿 $\omega_1=0$ 翻转后与 non-rephasing 谱相加，应当重现常规测得的吸收型 2D 谱。",
            r"波片色差与偏振片角度误差会转化为相位误差与干涉对比度下降，可以用线性自相关检验各相位设置。",
            r"不做相位循环、仅靠响应的因果性，也能在泵浦–探测几何中于频域分离 rephasing、non-rephasing 与 0Q/2Q 贡献（Timmer 2025）。",
        ],
        results=[
            F(r"$\lambda/4$ 波片的 Jones 矩阵", r"Q(\theta)=R(\theta)\begin{pmatrix}1&0\\ 0&i\end{pmatrix}R(-\theta)"),
            F("PC-TWINS 的相位设置", r"\theta_{\lambda/4}=45^\circ,\ 0^\circ,\ 90^\circ\;\Rightarrow\;\Delta\varphi_0=0,\ -\frac{\pi}{2},\ +\frac{\pi}{2};\qquad \mathrm{Pol}_2:\ +45^\circ\to-45^\circ\;\Rightarrow\;+\pi"),
            F("两步循环的组合（示意）", r"S_{R}\propto S(0)-i\,S\!\left(\tfrac{\pi}{2}\right),\qquad S_{NR}\propto S(0)+i\,S\!\left(\tfrac{\pi}{2}\right)",
              r"假设 rephasing $\propto e^{+i\Delta\varphi_0}$；与 $\Delta\varphi_0$ 无关的项落在 $\omega_1=0$ 另行扣除；符号随约定而变。"),
        ],
        readings=[
            R("Timmer2024", "里程碑论文", "首读", "全文，重点：图 1 的波片与偏振片设置、图 2 的相位验证、图 3 的 rephasing / non-rephasing 分离",
              "PC-TWINS 的原始论文；arXiv 版可免费阅读。"),
            R("Timmer2024SI", "里程碑论文", "重要", "第 1 节 TWINS 的定量描述；第 4 节 rephasing / non-rephasing 与 0Q/2Q 的数据处理",
              "正文略去的推导与数据处理细节都在补充材料里。"),
            R("Timmer2025", "里程碑论文", "重要", "全文",
              "仅用因果性分离信号的方法，可与相位循环方案对照。"),
            R("Myers2008", "里程碑论文", "重要", "数据处理各节",
              "Timmer 2024 分离 rephasing / non-rephasing 时直接引用的处理流程。"),
        ],
        terms=[
            T("PC-TWINS", "phase-cycling TWINS", r"在 TWINS 两偏振片之间加入消色差 $\lambda/4$ 波片以控制两泵浦脉冲相对相位的方案。"),
            T("相对绝对相位", "relative absolute phase", r"两泵浦脉冲载波–包络相位之差 $\Delta\varphi_0$，与延迟无关、在光谱上为常数。"),
            T("消色差四分之一波片", "achromatic quarter-wave plate", r"在宽光谱范围内引入近似恒定 $\pi/2$ 相位差的波片。"),
            T("复值信号", "complex-valued signal", "由相位循环或因果性得到的、频率符号正确的信号，可分出不同象限。"),
            T("因果性", "causality", "信号只能在最后一次光场作用之后出现，据此可约束时间域或频率域数据。"),
        ],
    ),
    dict(
        id="F20", zh="零量子与双量子 2DES", en="Zero- & double-quantum 2DES", short="零/双量子 2DES",
        layer=8, prereqs=["F19"], chapters=[35],
        why="双量子谱直接看到双激发态与多体关联（如双激子），是 PC-TWINS 相比普通泵浦–探测 2DES 新增的能力。",
        concepts=[
            r"双量子（2Q）信号探测基态与双激发态之间的相干 $|f\rangle\langle g|$；零量子（0Q）信号探测布居或激发态内部的相干。",
            r"对无相互作用（谐性）体系，两条 2Q 路径相互抵消，因此 2Q 信号直接反映多激子关联（Kim 等 2009）。",
            r"Timmer 2024 用反转的脉冲次序测 0Q/2Q：$T=0$、相干时间 $\tau<0$，探测光与第二泵浦重合，最后一次作用来自第一泵浦，因此激发轴要平移为 $\omega_\tau+\omega_t$。",
            r"0Q 谱线宽反映布居弛豫，2Q 谱线宽反映双量子退相；对 J 聚集体薄膜，Timmer 2024 报告的量级分别约为 140 fs 与 30 fs，双激子蓝移约 3 meV。",
            r"2Q 2DES 的标志性应用是半导体量子阱中的双激子与高阶电子关联。",
        ],
        results=[
            F("2Q 峰位", r"\omega_{2Q}\approx\omega_{eg}+\omega_{fe}=\omega_{fg}"),
            F("反转次序下的激发轴", r"\omega_{0Q/2Q}=\omega_\tau+\omega_t"),
            F("双激子移动", r"\Delta=E_{XX}-2E_X", r"Timmer 2024 估计 $\Delta\approx(3\pm 2)\,\mathrm{meV}$（蓝移）。"),
            F("谐性体系的 2Q 抵消", r"\omega_{fe}=\omega_{eg},\quad \mu_{fe}=\sqrt{2}\,\mu_{eg}\;\Rightarrow\;S_{2Q}=0"),
        ],
        readings=[
            R("Kim2009", "综述", "首读", "全文",
              "双量子相干 2DES 的入门综述，讲清双量子路径与多体关联的关系。"),
            R("Cai2024", "里程碑论文", "重要", "泵浦–探测几何下 2Q 信号的采集次序与数据处理",
              "Timmer 2024 的 0Q/2Q 采集与处理方案沿用此文。"),
            R("Stone2009", "里程碑论文", "重要", "全文，重点看双激子峰的分配",
              "2Q 2DES 在 GaAs 量子阱双激子上的标志性实验。"),
            R("Turner2010", "里程碑论文", "延伸", "全文",
              "把多量子 2D 光谱推向更高阶电子关联。"),
            R("Luttig2023", "综述", "延伸", "高阶信号的分类与提取方法",
              "高阶多维光谱与 0Q/2Q 方法的区别与互补。"),
        ],
        terms=[
            T("双量子相干", "double-quantum coherence", r"基态与双激发态之间的相干 $|f\rangle\langle g|$，频率约为两倍激发能。"),
            T("零量子", "zero-quantum", "相干阶数为零的路径（布居或激发态之间的相干），反映激发态动力学。"),
            T("双激子", "biexciton", "两个激子组成的束缚或关联态，其能量偏离两倍单激子能量。"),
            T("多体关联", "many-body correlation", "多个激发之间的相互作用，使体系响应偏离独立粒子之和。"),
        ],
    ),
    dict(
        id="F21", zh="标定、验收与伪信号", en="Calibration, acceptance tests & artefacts", short="标定与伪信号",
        layer=8, prereqs=["F19"], chapters=[36, 37],
        why="谱仪必须先证明“测到的是真的”：延迟轴、相位、背景与伪信号都要有可重复的标定方法与验收标准。",
        concepts=[
            r"延迟轴标定：参考光谱的傅里叶变换、楔片位置–延迟拟合与重复性统计，并给出量化的验收判据。",
            r"投影–切片关系：吸收型 2D 谱沿激发轴的投影应与同一等待时间的泵浦–探测谱一致，可用于交叉检验与定相。",
            r"可伪装成信号的误差：泵浦散射、延迟非线性、相位步误差、激光漂移与高阶信号；每一种都需要对应的诊断实验。",
            r"三阶信号应与泵浦能流成正比；偏离线性提示混入了高阶贡献，可用强度变化分离响应阶数（Krich 等 2025）。",
            r"光学厚样品、有限光束尺寸与探测方式会造成传播畸变，扭曲 2D 峰形（Yetzbacher 等 2007）。",
            r"准相位循环与斩波可消除散射；相位同步欠采样可以减少 $t_1$ 扫描点数。",
        ],
        results=[
            F("投影–切片关系", r"\int S_{\mathrm{abs}}(\omega_1,T,\omega_3)\,d\omega_1\propto S_{\mathrm{PP}}(T,\omega_3)"),
            F("三阶判据", r"S^{(3)}\propto F_{\mathrm{pump}}\quad\Longleftrightarrow\quad \frac{d\ln S}{d\ln F_{\mathrm{pump}}}=1"),
            F("延迟抖动造成的相位误差", r"\delta\varphi=\omega\,\sigma_\tau", r"例如 600 nm（$\omega\approx 3.14\ \mathrm{rad/fs}$）处 $\sigma_\tau=0.1\ \mathrm{fs}$ 对应约 0.31 rad。"),
        ],
        readings=[
            R("Timmer2025", "里程碑论文", "首读", "各类信号贡献在泵浦–探测几何中的位置与分离",
              "知道每种贡献会出现在谱的哪里，是识别伪信号的前提。"),
            R("Yetzbacher2007", "里程碑论文", "重要", "传播、几何与探测造成峰形畸变的结论部分",
              "判断峰形异常来自物理还是仪器的参考。"),
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
        layer=7, prereqs=["F17"], chapters=[38],
        why=r"2DES 数据是 $(\omega_1,T,\omega_3)$ 三维数组；全局分析、拍频分析与峰形分析把它压缩成可以写进论文的物理量。",
        concepts=[
            r"沿等待时间做全局多指数拟合，得到二维衰减相关谱（2D-DAS）。",
            r"对拟合残差沿 $T$ 做傅里叶变换得到拍频图，在 $\omega_1$–$\omega_3$ 平面上定位某一拍频的振幅分布；电子相干与振动相干的拍频图特征不同。",
            r"中心线斜率随 $T$ 的衰减给出频率涨落相关函数的时间常数。",
            r"SVD 或 PCA 用于估计数据中显著成分的个数，并用截断重构降噪。",
            r"DAS、EAS、SAS 分别对应平行衰减、顺序模型与目标模型；目标分析需要额外的动力学假设。",
            r"拟合参数需要报告不确定度（协方差矩阵或残差自助法）；pyglotaran 等开源工具可做全局与目标分析。",
        ],
        results=[
            F("全局多指数模型", r"S(\omega_1,T,\omega_3)=\sum_{k}A_k(\omega_1,\omega_3)\,e^{-T/\tau_k}"),
            F("奇异值分解", r"D=U\Sigma V^{\mathsf{T}}=\sum_i s_i\,\mathbf{u}_i\mathbf{v}_i^{\mathsf{T}}"),
            F("拍频图", r"B(\omega_1,\omega_2,\omega_3)=\left|\int r(\omega_1,T,\omega_3)\,e^{i\omega_2T}\,dT\right|", r"$r$ 为全局拟合残差。"),
            F("参数协方差（非线性最小二乘）", r"\mathrm{Cov}(\hat{\boldsymbol\theta})\approx\hat\sigma^{2}\left(J^{\mathsf{T}}J\right)^{-1}", r"$J$ 为残差对参数的 Jacobian。"),
        ],
        readings=[
            R("vanStokkum2004", "综述", "首读", "全局分析与目标分析的模型与参数估计各节",
              "全局与目标分析的标准参考，DAS、EAS、SAS 的定义都出自这里。"),
            R("Kwak2007", "里程碑论文", "重要", "CLS 方法的定义与适用条件",
              "从 2D 峰形提取频率涨落相关函数的常用方法。"),
            R("Jolliffe2016", "综述", "重要", "第 1–2 节：PCA 的定义与计算",
              "SVD 与 PCA 的现代简明综述。"),
            R("Shlens2014", "讲义", "延伸", "全文",
              "从线性代数直觉出发的 PCA 教程。"),
            R("Butkus2012", "里程碑论文", "延伸", "全文（4 页）",
              "拍频图中电子相干与振动相干的区分判据。"),
        ],
        terms=[
            T("全局分析", "global analysis", "用共享时间常数同时拟合所有波长（或所有 2D 像素）的数据。"),
            T("衰减相关谱", "decay-associated spectrum (DAS)", "全局多指数拟合中每个时间常数对应的振幅谱。"),
            T("拍频图", "beating map", r"某一振荡频率的振幅在 $\omega_1$–$\omega_3$ 平面上的分布。"),
            T("奇异值分解", "singular value decomposition (SVD)", "把数据矩阵分解为正交成分与奇异值，用于判断成分数与降噪。"),
        ],
    ),
    dict(
        id="F23", zh="原理总串联、系统改进与研究前沿", en="Synthesis, instrument improvements & research frontier", short="前沿与改进",
        layer=9, prereqs=["F20", "F21", "F22"], chapters=[39, 40],
        why="把光源、TWINS、样品、探测、相位循环与数据分析串成一条信号链，再看哪些环节可以改进、哪些问题仍然开放。",
        concepts=[
            r"信号链：光源 → TWINS 泵浦对（相位设置）→ 样品 → 探测光自外差 → 光谱仪与相机 → 相位循环组合 → 傅里叶变换与分析；每个环节都对应可测量的指标。",
            r"改进方向：采集速度（快速扫描、欠采样）、带宽（更宽的泵浦与探测）、相位精度（PC-TWINS）、新的检测通道（荧光、光电流、光电子）。",
            r"作用量检测（荧光、光电流）记录布居而非发射场，路径组合与相位循环要求与相干检测不同，还会出现非相干布居混合等额外贡献。",
            r"代表性应用：光合作用复合物中的能量转移与相干、半导体（如钙钛矿）中的载流子热化与多体效应。",
            r"高阶多维光谱与强度依赖分离响应阶数是当前的活跃方向。",
        ],
        results=[
            F("采集时间估计", r"t_{\mathrm{meas}}=\frac{N_{t_1}\,N_T\,N_{\mathrm{avg}}\,N_{\mathrm{PC}}}{f_{\mathrm{rep}}}",
              r"$N_{\mathrm{PC}}$ 为相位循环步数，$f_{\mathrm{rep}}$ 为有效测量重复频率（含斩波）。"),
            F("散粒噪声极限下的信噪比", r"\mathrm{SNR}\propto\sqrt{t_{\mathrm{meas}}}"),
        ],
        readings=[
            R("Biswas2022", "综述", "首读", "按与样品相关的章节选读",
              "近年最全面的 2DES 综述，用来定位研究前沿与开放问题。"),
            R("Luttig2023", "综述", "重要", "全文",
              "高阶多维与泵浦–探测光谱的最新进展。"),
            R("Draeger2017", "里程碑论文", "延伸", "快速扫描方案与采集效率",
              "作用量检测与快速扫描的代表性实现。"),
            R("Richter2017", "里程碑论文", "延伸", "全文",
              "用 2DES 研究钙钛矿载流子热化的例子。"),
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


# Characters that mean "math written as plain text" when they appear outside $...$.
MATH_OUTSIDE = re.compile(
    "[Ͱ-Ͽµ⁰-₟²³¹√∫⟨⟩"
    "≈≪≫±∓†×−∂∑∞\\^_\\\\]")


def split_math(text: str) -> tuple[list[str], list[str]]:
    """Split text into (outside, inside) segments on $...$ / $$...$$. Raises on unbalanced $."""
    outside, inside = [], []
    i, buf = 0, []
    while i < len(text):
        if text[i] == "$":
            delim = "$$" if text.startswith("$$", i) else "$"
            j = text.find(delim, i + len(delim))
            if j < 0:
                raise ValueError("未闭合的 $")
            outside.append("".join(buf))
            buf = []
            inside.append(text[i + len(delim):j])
            i = j + len(delim)
        else:
            buf.append(text[i])
            i += 1
    outside.append("".join(buf))
    return outside, inside


def tex_problems(tex: str) -> list[str]:
    problems = []
    if re.search(r"[^\x20-\x7e]", tex):
        bad = sorted(set(re.findall(r"[^\x20-\x7e]", tex)))
        problems.append(f"数学中含非 ASCII 字符 {bad}（请用 LaTeX 命令，如 \\omega）")
    depth = 0
    for k, ch in enumerate(tex):
        if ch in "{}" and k > 0 and tex[k - 1] == "\\":
            continue
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            break
    if depth != 0:
        problems.append("花括号不配对")
    if "$" in tex:
        problems.append("公式字段里不要再写 $")
    return problems


def check_text(where: str, text: str, errors: list[str]) -> None:
    try:
        outside, inside = split_math(text)
    except ValueError as e:
        errors.append(f"{where}: {e}: {text}")
        return
    for seg in outside:
        bad = MATH_OUTSIDE.findall(seg)
        if bad:
            errors.append(f"{where}: $...$ 之外出现数学符号 {sorted(set(bad))}，请写成 LaTeX: {text}")
    for seg in inside:
        for p in tex_problems(seg):
            errors.append(f"{where}: {p}: {text}")


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

    chapters_seen: set[int] = set()
    used_refs: set[str] = set()

    for m in MODULES:
        mid = m["id"]
        for field in ("zh", "en", "short", "why"):
            if not m.get(field):
                errors.append(f"{mid}: 缺少字段 {field}")
        check_text(f"{mid}.why", m["why"], errors)
        for field in ("zh", "en", "short"):
            check_text(f"{mid}.{field}", m[field], errors)
        if not isinstance(m.get("layer"), int) or m["layer"] < 0:
            errors.append(f"{mid}: layer 必须是非负整数")
        for p in m["prereqs"]:
            if p not in by_id:
                errors.append(f"{mid}: 前置模块 {p} 不存在")
            elif by_id[p]["layer"] >= m["layer"]:
                errors.append(f"{mid}（第 {m['layer']} 层）: 前置 {p} 位于第 {by_id[p]['layer']} 层，必须严格更低")
        if len(set(m["prereqs"])) != len(m["prereqs"]):
            errors.append(f"{mid}: 前置模块重复")

        # knowledge card
        n = len(m["concepts"])
        if not 3 <= n <= 6:
            errors.append(f"{mid}: 核心概念 {n} 条，应为 3–6 条")
        for k, c in enumerate(m["concepts"], 1):
            check_text(f"{mid}.concepts[{k}]", c, errors)
        n = len(m["results"])
        if not 2 <= n <= 5:
            errors.append(f"{mid}: 关键结果 {n} 条，应为 2–5 条")
        for k, r in enumerate(m["results"], 1):
            if not r["name"] or not r["tex"]:
                errors.append(f"{mid}.results[{k}]: 名称与公式都不能为空")
            check_text(f"{mid}.results[{k}].name", r["name"], errors)
            check_text(f"{mid}.results[{k}].note", r["note"], errors)
            for p in tex_problems(r["tex"]):
                errors.append(f"{mid}.results[{k}].tex: {p}")

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
            check_text(f"{mid}.readings[{r['ref']}].part", r["part"], errors)
            check_text(f"{mid}.readings[{r['ref']}].why", r["why"], errors)

        # term cards
        n = len(m["terms"])
        if not 3 <= n <= 6:
            errors.append(f"{mid}: 术语 {n} 条，应为 3–6 条")
        for t in m["terms"]:
            if not (t["zh"] and t["en"] and t["definition"]):
                errors.append(f"{mid}: 术语字段不完整 {t}")
            for field in ("zh", "en", "definition"):
                check_text(f"{mid}.terms[{t['zh']}].{field}", t[field], errors)

        for ch in m["chapters"]:
            if not 0 <= ch <= 40:
                errors.append(f"{mid}: 教材章节 {ch} 超出 0–40")
            chapters_seen.add(ch)

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
        cur = queue.pop()
        visited += 1
        for s in succ[cur]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if visited != len(MODULES):
        errors.append("依赖图存在环")

    missing = sorted(set(range(41)) - chapters_seen)
    if missing:
        warnings.append(f"教材章节未被任何模块覆盖: {missing}")
    unused = sorted(set(REFS) - used_refs)
    if unused:
        warnings.append(f"REFS 中未被引用的条目: {unused}")
    for key, ref in REFS.items():
        if not (ref.get("doi") or ref.get("arxiv") or ref.get("url")):
            errors.append(f"文献 {key} 没有 DOI、arXiv 或 URL")
        if "$" in ref["title"]:
            errors.append(f"文献 {key} 的标题含 $，会被当作公式渲染")

    if errors:
        raise DataError("\n".join(errors))
    return warnings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def build() -> dict:
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
            "chapters": m["chapters"], "concepts": m["concepts"], "results": m["results"],
            "readings": [{k: r[k] for k in ("ref", "type", "priority", "part", "why")} for r in m["readings"]],
            "terms": m["terms"],
        })
    return {
        "generated": date.today().isoformat(),
        "site": SITE,
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
    n_concepts = sum(len(m["concepts"]) for m in MODULES)
    n_results = sum(len(m["results"]) for m in MODULES)
    n_terms = sum(len(m["terms"]) for m in MODULES)
    print(f"校验通过：{len(MODULES)} 个模块，{1 + max(m['layer'] for m in MODULES)} 层，"
          f"{n_concepts} 条核心概念，{n_results} 个关键公式，{len(REFS)} 条文献，{n_terms} 张术语卡片。")
    if not args.check:
        write(data)
        print(f"已写入 {OUT.name}")
    if args.check_links:
        return check_links()
    return 0


if __name__ == "__main__":
    sys.exit(main())
