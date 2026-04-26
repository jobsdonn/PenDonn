"""PDF Report Generator — modern, professional security report layout."""

import json
import logging
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
INK      = colors.HexColor('#0F1117')   # near-black body text
SLATE    = colors.HexColor('#1E2A3A')   # dark navy — cover + section bars
MUTED    = colors.HexColor('#6B7280')   # secondary text
RULE     = colors.HexColor('#E5E7EB')   # table dividers
WHITE    = colors.white
RED      = colors.HexColor('#EF4444')   # critical
ORANGE   = colors.HexColor('#F97316')   # high
AMBER    = colors.HexColor('#F59E0B')   # medium
SKY      = colors.HexColor('#38BDF8')   # low / info
GREEN    = colors.HexColor('#10B981')   # success
ACCENT   = colors.HexColor('#6366F1')   # indigo — cover accent + links

SEV_COLOR = {
    'critical': RED,
    'high':     ORANGE,
    'medium':   AMBER,
    'low':      SKY,
    'info':     MUTED,
}


# ---------------------------------------------------------------------------
# Page templates with header/footer callbacks
# ---------------------------------------------------------------------------
class _ReportDoc(BaseDocTemplate):
    def __init__(self, path, report_date, **kw):
        super().__init__(path, **kw)
        self.report_date = report_date
        self._build_templates()

    def _build_templates(self):
        W, H = self.pagesize
        m = self.leftMargin

        # Cover: full bleed, no header/footer
        cover_frame = Frame(0, 0, W, H, leftPadding=0, rightPadding=0,
                            topPadding=0, bottomPadding=0, id='cover')
        cover_tpl = PageTemplate(id='Cover', frames=[cover_frame],
                                 onPage=self._cover_page)

        # Body pages with footer
        body_frame = Frame(m, 20*mm, W - 2*m, H - m - 20*mm,
                           leftPadding=0, rightPadding=0,
                           topPadding=0, bottomPadding=0, id='body')
        body_tpl = PageTemplate(id='Body', frames=[body_frame],
                                onPage=self._body_page)

        self.addPageTemplates([cover_tpl, body_tpl])

    def _cover_page(self, canvas, doc):
        W, H = doc.pagesize
        # Dark background
        canvas.setFillColor(SLATE)
        canvas.rect(0, 0, W, H, fill=1, stroke=0)
        # Accent bar on left
        canvas.setFillColor(ACCENT)
        canvas.rect(0, 0, 6*mm, H, fill=1, stroke=0)

    def _body_page(self, canvas, doc):
        W, H = doc.pagesize
        # Thin top rule
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, H - 12*mm, W - doc.rightMargin, H - 12*mm)
        # Footer
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 12*mm,
                          f'PenDonn  ·  Confidential  ·  {doc.report_date}')
        canvas.drawRightString(W - doc.rightMargin, 12*mm,
                               f'Page {doc.page}')


# ---------------------------------------------------------------------------
# Style factory
# ---------------------------------------------------------------------------
def _styles():
    base = getSampleStyleSheet()
    add = {}

    def s(name, **kw):
        add[name] = ParagraphStyle(name, parent=base['Normal'], **kw)

    # Cover
    s('CoverTitle', fontSize=36, leading=42, textColor=WHITE,
      fontName='Helvetica-Bold', spaceBefore=0, spaceAfter=4)
    s('CoverSub',   fontSize=14, leading=18, textColor=colors.HexColor('#CBD5E1'),
      fontName='Helvetica', spaceAfter=0)
    s('CoverMeta',  fontSize=9,  leading=14, textColor=colors.HexColor('#94A3B8'),
      fontName='Helvetica')

    # Body
    s('SectionLabel', fontSize=8, leading=10, textColor=ACCENT,
      fontName='Helvetica-Bold', spaceBefore=20, spaceAfter=4,
      letterSpacing=1.5)
    s('H2', fontSize=16, leading=20, textColor=INK,
      fontName='Helvetica-Bold', spaceBefore=0, spaceAfter=8)
    s('H3', fontSize=11, leading=14, textColor=INK,
      fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4)
    s('Body', fontSize=9, leading=14, textColor=INK, spaceAfter=4)
    s('BodyMuted', fontSize=9, leading=14, textColor=MUTED, spaceAfter=4)
    s('Mono', fontSize=8, leading=12, textColor=INK,
      fontName='Courier', spaceAfter=2)
    s('Disclaimer', fontSize=8, leading=12, textColor=MUTED,
      fontName='Helvetica-Oblique', spaceBefore=8)

    return {**{k: base[k] for k in base.byName}, **add}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rule(color=RULE, thickness=0.5):
    return HRFlowable(width='100%', thickness=thickness,
                      color=color, spaceAfter=8, spaceBefore=0)


def _sev_badge(sev):
    """Inline HTML fragment for a severity badge (used inside Paragraph)."""
    c = {'critical': '#EF4444', 'high': '#F97316',
         'medium': '#F59E0B', 'low': '#38BDF8'}.get(sev.lower(), '#6B7280')
    label = sev.upper()
    return f'<font color="{c}"><b>{label}</b></font>'


def _table(data, col_widths, header_fill=SLATE, stripe=colors.HexColor('#F8FAFC')):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    n = len(data)
    style = [
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0),  header_fill),
        ('TEXTCOLOR',    (0, 0), (-1, 0),  WHITE),
        ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0),  8),
        ('TOPPADDING',   (0, 0), (-1, 0),  6),
        ('BOTTOMPADDING',(0, 0), (-1, 0),  6),
        # Body
        ('FONTSIZE',     (0, 1), (-1, -1), 8),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('TEXTCOLOR',    (0, 1), (-1, -1), INK),
        ('ALIGN',        (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        # Horizontal rules only (clean look)
        ('LINEBELOW',    (0, 0), (-1, 0),  0.5, SLATE),
    ]
    # Alternating stripe
    for row in range(1, n, 2):
        style.append(('BACKGROUND', (0, row), (-1, row), stripe))
    t.setStyle(TableStyle(style))
    return t


def _stat_row(items, col_width, ST):
    """A row of stat boxes: [(label, value, sub), ...]"""
    cells = []
    for label, value, sub in items:
        inner = Table(
            [[Paragraph(str(value), ParagraphStyle(
                '__sv', fontSize=22, leading=26,
                fontName='Helvetica-Bold', textColor=INK))],
             [Paragraph(label, ParagraphStyle(
                '__sl', fontSize=8, leading=11,
                fontName='Helvetica-Bold', textColor=MUTED,
                letterSpacing=0.8))],
             [Paragraph(sub or '', ParagraphStyle(
                '__ss', fontSize=7, leading=10,
                fontName='Helvetica', textColor=MUTED))]],
            colWidths=[col_width - 8*mm],
        )
        inner.setStyle(TableStyle([
            ('ALIGN',  (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        cells.append(inner)

    outer = Table([cells], colWidths=[col_width]*len(items))
    outer.setStyle(TableStyle([
        ('BOX',       (0, 0), (-1, -1), 0.5, RULE),
        ('LINEAFTER', (0, 0), (-2, -1), 0.5, RULE),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    return outer


def _section_header(label, title, ST):
    return [
        Paragraph(label.upper(), ST['SectionLabel']),
        Paragraph(title, ST['H2']),
        _rule(),
    ]


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------
class PDFReport:
    """Modern, professional PDF pentest report generator."""

    def __init__(self, db, output_path=None):
        self.db = db
        if output_path:
            self.output_path = output_path
        else:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.output_path = f'./data/pendonn_report_{ts}.pdf'
        self.ST = _styles()
        self.story = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate_report(self, include_sections=None):
        if include_sections is None:
            include_sections = [
                'summary', 'networks', 'handshakes', 'passwords',
                'scans', 'vulnerabilities', 'recommendations',
            ]

        report_date = datetime.now().strftime('%d %B %Y')
        doc = _ReportDoc(
            self.output_path,
            report_date=report_date,
            pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=16*mm, bottomMargin=16*mm,
        )

        self._cover(report_date)
        self.story.append(NextPageTemplate('Body'))
        self.story.append(PageBreak())

        if 'summary'         in include_sections: self._summary()
        if 'networks'        in include_sections: self._networks()
        if 'handshakes'      in include_sections: self._handshakes()
        if 'passwords'       in include_sections: self._passwords()
        if 'scans'           in include_sections: self._scans()
        if 'vulnerabilities' in include_sections: self._vulnerabilities()
        if 'recommendations' in include_sections: self._recommendations()

        doc.build(self.story)
        logger.info('PDF report generated: %s', self.output_path)
        return self.output_path

    # ------------------------------------------------------------------
    # Cover
    # ------------------------------------------------------------------
    def _cover(self, report_date):
        W, H = A4
        lm = 20*mm

        def spacer(h): self.story.append(Spacer(1, h))

        spacer(H * 0.25)

        # Left-indent everything by wrapping in a table
        def row(p):
            t = Table([[p]], colWidths=[W - lm - 6*mm - 20*mm])
            t.setStyle(TableStyle([
                ('LEFTPADDING',  (0,0),(-1,-1), lm),
                ('TOPPADDING',   (0,0),(-1,-1), 0),
                ('BOTTOMPADDING',(0,0),(-1,-1), 0),
            ]))
            self.story.append(t)

        row(Paragraph('PenDonn', self.ST['CoverTitle']))
        spacer(3*mm)
        row(Paragraph('Wireless Penetration Testing Report', self.ST['CoverSub']))
        spacer(16*mm)

        # Thin accent rule
        rule_t = Table([['']], colWidths=[80*mm])
        rule_t.setStyle(TableStyle([
            ('LINEABOVE',    (0,0),(-1,-1), 1.5, ACCENT),
            ('LEFTPADDING',  (0,0),(-1,-1), lm),
            ('TOPPADDING',   (0,0),(-1,-1), 0),
            ('BOTTOMPADDING',(0,0),(-1,-1), 0),
        ]))
        self.story.append(rule_t)
        spacer(8*mm)

        row(Paragraph(f'Generated: {report_date}', self.ST['CoverMeta']))
        spacer(2*mm)
        row(Paragraph('Classification: CONFIDENTIAL', self.ST['CoverMeta']))
        spacer(2*mm)
        row(Paragraph('Authorized pentest — Kjell &amp; Company', self.ST['CoverMeta']))

    # ------------------------------------------------------------------
    # Executive summary
    # ------------------------------------------------------------------
    def _summary(self):
        ST = self.ST
        s = self.story
        stats = self.db.get_statistics()

        for p in _section_header('01', 'Executive Summary', ST):
            s.append(p)

        conn = self.db.connect()
        cur  = conn.cursor()
        cur.execute('SELECT severity, COUNT(*) c FROM vulnerabilities GROUP BY severity')
        sc = {r['severity']: r['c'] for r in cur.fetchall()}

        nd  = stats.get('networks_discovered', 0)
        hc  = stats.get('handshakes_captured', 0)
        pc  = stats.get('passwords_cracked', 0)
        vf  = stats.get('vulnerabilities_found', 0)
        crit = sc.get('critical', 0)
        high = sc.get('high', 0)

        W = A4[0] - 40*mm
        cw = W / 4
        s.append(_stat_row([
            ('NETWORKS',   nd,  'discovered'),
            ('HANDSHAKES', hc,  'captured'),
            ('PASSWORDS',  pc,  'cracked'),
            ('VULNS',      vf,  f'{crit} critical · {high} high'),
        ], cw, ST))
        s.append(Spacer(1, 10*mm))

        # Brief narrative
        risk = 'HIGH' if crit > 0 else ('MEDIUM' if high > 0 else 'LOW')
        risk_color = {'HIGH': '#EF4444', 'MEDIUM': '#F59E0B', 'LOW': '#10B981'}[risk]
        body = (
            f'This report documents the results of an automated wireless pentest. '
            f'<b>{nd}</b> network{"s" if nd != 1 else ""} were discovered, '
            f'<b>{hc}</b> WPA handshake{"s" if hc != 1 else ""} captured, and '
            f'<b>{pc}</b> password{"s" if pc != 1 else ""} recovered. '
            f'Post-compromise enumeration identified <b>{vf}</b> '
            f'issue{"s" if vf != 1 else ""} across the internal network. '
            f'Overall risk rating: <font color="{risk_color}"><b>{risk}</b></font>.'
        )
        s.append(Paragraph(body, ST['Body']))
        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Networks
    # ------------------------------------------------------------------
    def _networks(self):
        ST = self.ST
        s  = self.story
        nets = self.db.get_networks()

        for p in _section_header('02', 'Discovered Networks', ST):
            s.append(p)

        if not nets:
            s.append(Paragraph('No networks recorded.', ST['BodyMuted']))
            s.append(PageBreak())
            return

        W  = A4[0] - 40*mm
        data = [['SSID', 'BSSID', 'CH', 'ENC', 'dBm']]
        for n in nets[:60]:
            data.append([
                n.get('ssid') or '(hidden)',
                n.get('bssid', ''),
                str(n.get('channel', '')),
                n.get('encryption', ''),
                str(n.get('signal_strength', '')),
            ])
        s.append(_table(data, [W*0.30, W*0.25, W*0.08, W*0.20, W*0.17]))
        if len(nets) > 60:
            s.append(Paragraph(f'… and {len(nets)-60} more.', ST['BodyMuted']))
        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Handshakes
    # ------------------------------------------------------------------
    def _handshakes(self):
        ST = self.ST
        s  = self.story
        conn = self.db.connect()
        cur  = conn.cursor()
        cur.execute('SELECT * FROM handshakes ORDER BY id DESC')
        rows = [dict(r) for r in cur.fetchall()]

        for p in _section_header('03', 'Captured Handshakes', ST):
            s.append(p)

        if not rows:
            s.append(Paragraph('No handshakes captured.', ST['BodyMuted']))
            s.append(PageBreak())
            return

        W    = A4[0] - 40*mm
        data = [['SSID', 'BSSID', 'CAPTURED', 'STATUS']]
        for r in rows:
            ts = (r.get('capture_date') or '')[:19]
            st = (r.get('status') or 'pending').upper()
            data.append([r.get('ssid', ''), r.get('bssid', ''), ts, st])

        t = _table(data, [W*0.28, W*0.28, W*0.28, W*0.16])
        # Color the status column (setStyle is additive in ReportLab)
        t.setStyle(TableStyle([
            ('TEXTCOLOR', (3, i), (3, i),
             GREEN if (rows[i-1].get('status', '') == 'cracked') else MUTED)
            for i in range(1, len(rows)+1)
        ]))
        s.append(t)
        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Passwords
    # ------------------------------------------------------------------
    def _passwords(self):
        ST  = self.ST
        s   = self.story
        pwd = self.db.get_cracked_passwords()

        for p in _section_header('04', 'Recovered Credentials', ST):
            s.append(p)

        if not pwd:
            s.append(Paragraph('No passwords recovered.', ST['BodyMuted']))
            s.append(PageBreak())
            return

        W    = A4[0] - 40*mm
        data = [['SSID', 'BSSID', 'PASSWORD', 'CRACKED']]
        for r in pwd:
            ts = (r.get('cracked_date') or '')[:19]
            data.append([
                r.get('ssid', ''),
                r.get('bssid', ''),
                r.get('password', ''),
                ts,
            ])

        t = _table(data, [W*0.22, W*0.26, W*0.26, W*0.26],
                   header_fill=colors.HexColor('#7F1D1D'),
                   stripe=colors.HexColor('#FEF2F2'))
        # Make password column monospaced
        t.setStyle(TableStyle([
            ('FONTNAME', (2, 1), (2, -1), 'Courier'),
        ]))
        s.append(t)
        s.append(Spacer(1, 4*mm))
        s.append(Paragraph(
            'Passwords above are captured WPA PSKs and should be treated as '
            'highly sensitive. Rotate immediately.',
            ST['Disclaimer'],
        ))
        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Scans
    # ------------------------------------------------------------------
    def _scans(self):
        ST    = self.ST
        s     = self.story
        scans = self.db.get_scans()

        for p in _section_header('05', 'Network Enumeration', ST):
            s.append(p)

        if not scans:
            s.append(Paragraph('No enumeration scans recorded.', ST['BodyMuted']))
            s.append(PageBreak())
            return

        W = A4[0] - 40*mm

        for scan in scans:
            ssid  = scan.get('ssid') or 'Unknown'
            ts    = (scan.get('start_time') or '')[:19]
            vf    = scan.get('vulnerabilities_found', 0)
            st    = (scan.get('status') or 'unknown').upper()

            s.append(Paragraph(f'{ssid}', ST['H3']))
            s.append(Paragraph(
                f'Started: {ts}&nbsp;&nbsp;·&nbsp;&nbsp;Status: {st}'
                f'&nbsp;&nbsp;·&nbsp;&nbsp;Findings: {vf}',
                ST['BodyMuted'],
            ))
            s.append(Spacer(1, 3*mm))

            # Parse host list
            try:
                raw = scan.get('results', '{}')
                rd  = json.loads(raw) if isinstance(raw, str) else (raw or {})
                hosts = rd.get('phases', {}).get('port_scan', {}).get('results', [])
            except Exception:
                hosts = []

            if hosts:
                hdata = [['HOST', 'HOSTNAME', 'OPEN PORTS']]
                for h in hosts:
                    ports = ', '.join(
                        f"{p['port']}/{p.get('service','')}"
                        for p in (h.get('ports') or [])
                        if isinstance(p, dict)
                    ) or '—'
                    hdata.append([
                        h.get('ip', ''),
                        h.get('hostname', '') or '—',
                        ports,
                    ])
                s.append(_table(hdata, [W*0.22, W*0.28, W*0.50]))
            else:
                s.append(Paragraph('No host data recorded.', ST['BodyMuted']))

            s.append(Spacer(1, 6*mm))

        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Vulnerabilities
    # ------------------------------------------------------------------
    def _vulnerabilities(self):
        ST    = self.ST
        s     = self.story
        vulns = self.db.get_vulnerabilities()

        for p in _section_header('06', 'Vulnerabilities', ST):
            s.append(p)

        if not vulns:
            s.append(Paragraph('No vulnerabilities recorded.', ST['BodyMuted']))
            s.append(PageBreak())
            return

        W = A4[0] - 40*mm

        by_sev = {'critical': [], 'high': [], 'medium': [], 'low': [], 'info': []}
        for v in vulns:
            sev = (v.get('severity') or 'info').lower()
            by_sev.setdefault(sev, []).append(v)

        for sev in ('critical', 'high', 'medium', 'low', 'info'):
            group = by_sev.get(sev, [])
            if not group:
                continue

            c = SEV_COLOR.get(sev, MUTED)
            header_hex = {
                'critical': '#7F1D1D', 'high': '#7C2D12',
                'medium':   '#78350F', 'low':  '#0C4A6E', 'info': '#1F2937',
            }.get(sev, '#1E2A3A')

            s.append(Paragraph(
                f'{sev.upper()}  ({len(group)})',
                ParagraphStyle(f'__sh_{sev}', fontSize=9, leading=12,
                               textColor=c, fontName='Helvetica-Bold',
                               spaceBefore=6, spaceAfter=4),
            ))

            data = [['HOST : PORT', 'TYPE', 'DESCRIPTION']]
            for v in group[:30]:
                host = v.get('host', '')
                port = v.get('port', '')
                loc  = f'{host}:{port}' if port else host
                vtype = (v.get('vulnerability_type') or v.get('vuln_type') or '—')
                desc  = (v.get('description') or '—')[:120]
                data.append([loc, vtype, desc])

            s.append(_table(data, [W*0.25, W*0.25, W*0.50],
                            header_fill=colors.HexColor(header_hex)))
            if len(group) > 30:
                s.append(Paragraph(f'… {len(group)-30} more.', ST['BodyMuted']))
            s.append(Spacer(1, 4*mm))

        s.append(PageBreak())

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    def _recommendations(self):
        ST = self.ST
        s  = self.story

        for p in _section_header('07', 'Recommendations', ST):
            s.append(p)

        recs = [
            ('Use WPA3 where supported',
             'WPA3 replaces the PMKID-vulnerable 4-way handshake with SAE, '
             'eliminating offline dictionary attacks.'),
            ('Enforce strong passphrases (≥16 chars)',
             'Short or common PSKs are recoverable in seconds with rockyou.txt. '
             'Use a random passphrase generator.'),
            ('Disable WPS on all access points',
             'WPS PIN attacks bypass PSK strength entirely. '
             'Most consumer AP firmware has it enabled by default.'),
            ('Separate guest and production networks',
             'VLAN segmentation limits blast radius: a cracked guest PSK '
             'should not expose internal hosts.'),
            ('Patch and update AP firmware regularly',
             'Many older firmware versions expose PMKID without a connected '
             'client, making capture trivially easy.'),
            ('Enable 802.11w (Management Frame Protection)',
             'Prevents unauthenticated deauth frames, making handshake '
             'capture harder.'),
            ('Monitor for rogue APs',
             'Deploy wireless IDS (e.g. Kismet, Mist AI) to detect evil-twin '
             'attacks and unauthorized SSIDs.'),
        ]

        W = A4[0] - 40*mm
        for i, (title, detail) in enumerate(recs, 1):
            s.append(Paragraph(
                f'<b>{i}. {title}</b>',
                ParagraphStyle(f'__rh', fontSize=9, leading=13,
                               textColor=INK, fontName='Helvetica-Bold',
                               spaceBefore=6, spaceAfter=2),
            ))
            s.append(Paragraph(detail, ST['BodyMuted']))
            if i < len(recs):
                s.append(_rule(thickness=0.3))

        s.append(Spacer(1, 12*mm))
        s.append(Paragraph(
            'This report was generated automatically by PenDonn. '
            'All testing was conducted on networks with explicit written authorisation. '
            'Findings should be validated by a qualified security engineer before '
            'remediation actions are taken.',
            ST['Disclaimer'],
        ))


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def generate_pdf_report(db, output_path=None, include_sections=None):
    return PDFReport(db, output_path).generate_report(include_sections)
