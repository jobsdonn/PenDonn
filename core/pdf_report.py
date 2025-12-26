"""
PDF Report Generator

Generates comprehensive PDF reports from scan results with
charts, tables, and detailed vulnerability information.

Author: PenDonn Team
"""

import logging
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import VerticalBarChart
from io import BytesIO
import os

class PDFReport:
    """PDF report generator for PenDonn"""
    
    def __init__(self, db, output_path=None):
        """
        Initialize PDF report generator
        
        Args:
            db: Database instance
            output_path: Path to save PDF (default: auto-generated)
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
        
        # Output path
        if output_path:
            self.output_path = output_path
        else:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.output_path = f"./data/pendonn_report_{timestamp}.pdf"
        
        # Styles
        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        
        # Story (content list)
        self.story = []
    
    def _create_custom_styles(self):
        """Create custom paragraph styles"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))
        
        # Section header
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#3498db'),
            spaceAfter=12,
            spaceBefore=12,
            borderPadding=5
        ))
        
        # Subsection header
        self.styles.add(ParagraphStyle(
            name='SubsectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=10,
            spaceBefore=10
        ))
        
        # Critical alert
        self.styles.add(ParagraphStyle(
            name='CriticalAlert',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#c0392b'),
            spaceAfter=6,
            leftIndent=20
        ))
        
        # High alert
        self.styles.add(ParagraphStyle(
            name='HighAlert',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#e74c3c'),
            spaceAfter=6,
            leftIndent=20
        ))
        
        # Medium alert
        self.styles.add(ParagraphStyle(
            name='MediumAlert',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#f39c12'),
            spaceAfter=6,
            leftIndent=20
        ))
        
        # Low alert
        self.styles.add(ParagraphStyle(
            name='LowAlert',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#95a5a6'),
            spaceAfter=6,
            leftIndent=20
        ))
    
    def generate_report(self, include_sections=None):
        """
        Generate comprehensive PDF report
        
        Args:
            include_sections: List of sections to include (default: all)
                ['summary', 'networks', 'handshakes', 'passwords', 
                 'scans', 'vulnerabilities', 'recommendations']
        
        Returns:
            str: Path to generated PDF
        """
        self.logger.info("Generating PDF report")
        
        if include_sections is None:
            include_sections = [
                'summary', 'networks', 'handshakes', 'passwords',
                'scans', 'vulnerabilities', 'recommendations'
            ]
        
        # Create document
        doc = SimpleDocTemplate(
            self.output_path,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=1*inch,
            bottomMargin=0.75*inch
        )
        
        # Build content
        self._add_title_page()
        
        if 'summary' in include_sections:
            self._add_executive_summary()
        
        if 'networks' in include_sections:
            self._add_networks_section()
        
        if 'handshakes' in include_sections:
            self._add_handshakes_section()
        
        if 'passwords' in include_sections:
            self._add_passwords_section()
        
        if 'scans' in include_sections:
            self._add_scans_section()
        
        if 'vulnerabilities' in include_sections:
            self._add_vulnerabilities_section()
        
        if 'recommendations' in include_sections:
            self._add_recommendations_section()
        
        # Build PDF
        try:
            doc.build(self.story)
            self.logger.info(f"PDF report generated: {self.output_path}")
            return self.output_path
        except Exception as e:
            self.logger.error(f"Failed to generate PDF: {e}")
            raise
    
    def _add_title_page(self):
        """Add title page"""
        # Title
        title = Paragraph("PenDonn", self.styles['CustomTitle'])
        self.story.append(title)
        self.story.append(Spacer(1, 0.2*inch))
        
        subtitle = Paragraph(
            "Penetration Testing Report",
            self.styles['Heading2']
        )
        self.story.append(subtitle)
        self.story.append(Spacer(1, 0.5*inch))
        
        # Report info
        report_date = datetime.now().strftime('%B %d, %Y')
        info_data = [
            ['Report Date:', report_date],
            ['Generated By:', 'PenDonn Automated System'],
            ['Report Type:', 'Comprehensive Security Assessment']
        ]
        
        info_table = Table(info_data, colWidths=[2*inch, 4*inch])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        self.story.append(info_table)
        self.story.append(Spacer(1, 0.5*inch))
        
        # Disclaimer
        disclaimer = Paragraph(
            "<b>LEGAL DISCLAIMER:</b> This report contains sensitive security "
            "information and should be handled with care. Unauthorized access to "
            "computer networks is illegal. This testing was authorized and performed "
            "for security assessment purposes only.",
            self.styles['Normal']
        )
        self.story.append(disclaimer)
        
        self.story.append(PageBreak())
    
    def _add_executive_summary(self):
        """Add executive summary section"""
        self.story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        # Get statistics
        stats = self.db.get_statistics()
        
        # Summary text
        summary_text = f"""
        This report presents the findings from an automated penetration test 
        conducted using PenDonn. The assessment identified <b>{stats.get('networks_discovered', 0)}</b> 
        wireless networks, captured <b>{stats.get('handshakes_captured', 0)}</b> handshakes, 
        and cracked <b>{stats.get('passwords_cracked', 0)}</b> passwords.
        """
        
        self.story.append(Paragraph(summary_text, self.styles['Normal']))
        self.story.append(Spacer(1, 0.3*inch))
        
        # Get vulnerability counts by severity
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT severity, COUNT(*) as count FROM vulnerabilities GROUP BY severity')
        vuln_counts = {row['severity']: row['count'] for row in cursor.fetchall()}
        conn.close()
        
        critical = vuln_counts.get('critical', 0)
        high = vuln_counts.get('high', 0)
        medium = vuln_counts.get('medium', 0)
        low = vuln_counts.get('low', 0)
        
        stats_data = [
            ['Metric', 'Count'],
            ['Networks Discovered', str(stats.get('networks_discovered', 0))],
            ['Handshakes Captured', str(stats.get('handshakes_captured', 0))],
            ['Passwords Cracked', str(stats.get('passwords_cracked', 0))],
            ['Network Scans', str(stats.get('scans_completed', 0))],
            ['Critical Vulnerabilities', str(critical)],
            ['High Vulnerabilities', str(high)],
            ['Medium Vulnerabilities', str(medium)],
            ['Low Vulnerabilities', str(low)],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
        ]))
        
        self.story.append(stats_table)
        self.story.append(Spacer(1, 0.3*inch))
        
        # Severity chart
        if critical + high + medium + low > 0:
            self._add_vulnerability_chart(critical, high, medium, low)
        
        self.story.append(PageBreak())
    
    def _add_vulnerability_chart(self, critical, high, medium, low):
        """Add pie chart for vulnerability severity"""
        drawing = Drawing(400, 200)
        
        pie = Pie()
        pie.x = 150
        pie.y = 50
        pie.width = 120
        pie.height = 120
        
        pie.data = [critical, high, medium, low]
        pie.labels = [
            f'Critical ({critical})',
            f'High ({high})',
            f'Medium ({medium})',
            f'Low ({low})'
        ]
        pie.slices.strokeWidth = 0.5
        pie.slices[0].fillColor = colors.HexColor('#c0392b')  # Critical - dark red
        pie.slices[1].fillColor = colors.HexColor('#e74c3c')  # High - red
        pie.slices[2].fillColor = colors.HexColor('#f39c12')  # Medium - orange
        pie.slices[3].fillColor = colors.HexColor('#95a5a6')  # Low - grey
        
        drawing.add(pie)
        self.story.append(drawing)
        self.story.append(Spacer(1, 0.2*inch))
    
    def _add_networks_section(self):
        """Add discovered networks section"""
        self.story.append(Paragraph("Discovered Networks", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        # Get networks from database
        networks = self.db.get_networks()
        
        if not networks:
            self.story.append(Paragraph("No networks discovered.", self.styles['Normal']))
            self.story.append(PageBreak())
            return
        
        # Networks table
        table_data = [['SSID', 'BSSID', 'Channel', 'Encryption', 'Signal']]
        
        for net in networks[:50]:  # Limit to 50 networks
            table_data.append([
                net.get('ssid', 'N/A'),
                net.get('bssid', 'N/A'),
                str(net.get('channel', 'N/A')),
                net.get('encryption', 'N/A'),
                str(net.get('signal_strength', 'N/A'))
            ])
        
        networks_table = Table(table_data, colWidths=[1.5*inch, 1.5*inch, 0.8*inch, 1.2*inch, 0.8*inch])
        networks_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
        ]))
        
        self.story.append(networks_table)
        self.story.append(PageBreak())
    
    def _add_handshakes_section(self):
        """Add handshakes section"""
        self.story.append(Paragraph("Captured Handshakes", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        # Get all handshakes via raw query
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM handshakes')
        handshakes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        if not handshakes:
            self.story.append(Paragraph("No handshakes captured.", self.styles['Normal']))
            self.story.append(PageBreak())
            return
        
        table_data = [['SSID', 'BSSID', 'Captured', 'Status']]
        
        for hs in handshakes:
            capture_date = hs.get('capture_date', 'N/A')
            if capture_date != 'N/A':
                capture_date = capture_date[:19]
            table_data.append([
                hs.get('ssid', 'N/A'),
                hs.get('bssid', 'N/A'),
                capture_date,
                hs.get('status', 'pending').title()
            ])
        
        hs_table = Table(table_data, colWidths=[2*inch, 2*inch, 1.5*inch, 1*inch])
        hs_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')])
        ]))
        
        self.story.append(hs_table)
        self.story.append(PageBreak())
    
    def _add_passwords_section(self):
        """Add cracked passwords section"""
        self.story.append(Paragraph("Cracked Passwords", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        passwords = self.db.get_cracked_passwords()
        
        if not passwords:
            self.story.append(Paragraph("No passwords cracked yet.", self.styles['Normal']))
            self.story.append(PageBreak())
            return
        
        # Create table with same style as handshakes
        table_data = [['SSID', 'BSSID', 'Password', 'Cracked Date']]
        
        for pwd in passwords:
            ssid = pwd.get('ssid', 'Unknown')
            bssid = pwd.get('bssid', 'N/A')
            password = pwd.get('password', 'N/A')
            cracked_date = pwd.get('cracked_date', 'N/A')
            if cracked_date != 'N/A':
                cracked_date = cracked_date[:19]
            
            table_data.append([ssid, bssid, password, cracked_date])
        
        pwd_table = Table(table_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 1.5*inch])
        pwd_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#fadbd8'), colors.white]),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        self.story.append(pwd_table)
        self.story.append(PageBreak())
    
    def _add_scans_section(self):
        """Add network scans section"""
        self.story.append(Paragraph("Network Scans", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        scans = self.db.get_scans()
        
        if not scans:
            self.story.append(Paragraph("No network scans performed.", self.styles['Normal']))
            self.story.append(PageBreak())
            return
        
        import json
        for scan in scans:
            ssid = scan.get('ssid', 'Unknown')
            start_time = scan.get('start_time', 'N/A')
            if start_time != 'N/A':
                start_time = start_time[:19]
            scan_text = f"<b>Scan #{scan.get('id')}</b> - {ssid} ({start_time})"
            self.story.append(Paragraph(scan_text, self.styles['SubsectionHeader']))
            
            # Parse results JSON to get host details
            results = scan.get('results', '{}')
            hosts = []
            try:
                results_data = json.loads(results) if isinstance(results, str) else results
                # Get hosts from phases.port_scan.results path
                if 'phases' in results_data and 'port_scan' in results_data['phases']:
                    hosts = results_data['phases']['port_scan'].get('results', [])
                hosts_found = len(hosts)
            except Exception as e:
                hosts = []
                hosts_found = 0
            
            status = scan.get('status', 'unknown')
            vuln_count = scan.get('vulnerabilities_found', 0)
            self.story.append(Paragraph(f"<b>Status:</b> {status.title()}", self.styles['Normal']))
            self.story.append(Paragraph(f"<b>Hosts Found:</b> {hosts_found}", self.styles['Normal']))
            self.story.append(Paragraph(f"<b>Vulnerabilities Found:</b> {vuln_count}", self.styles['Normal']))
            self.story.append(Spacer(1, 0.2*inch))
            
            # Show detailed host information if available
            if hosts:
                for host in hosts:
                    ip = host.get('ip', 'N/A')
                    hostname = host.get('hostname', 'Unknown') or 'Unknown'
                    os_info = host.get('os', '') or 'Unknown'
                    ports_info = host.get('ports', [])
                    
                    # Host header
                    host_header = f"<b>Host: {ip}</b>"
                    if hostname and hostname != 'Unknown':
                        host_header += f" ({hostname})"
                    self.story.append(Paragraph(host_header, self.styles['SubsectionHeader']))
                    
                    if os_info and os_info != 'Unknown':
                        self.story.append(Paragraph(f"OS: {os_info}", self.styles['Normal']))
                    
                    # Port details table
                    if ports_info:
                        port_data = [['Port', 'Service', 'Product', 'Version']]
                        
                        for port_detail in ports_info:
                            port_num = port_detail.get('port', 'N/A')
                            service = port_detail.get('service', 'unknown')
                            product = port_detail.get('product', '')
                            version = port_detail.get('version', '')
                            
                            port_data.append([
                                str(port_num),
                                service,
                                product or '-',
                                version or '-'
                            ])
                        
                        port_table = Table(port_data, colWidths=[0.8*inch, 1.2*inch, 2*inch, 1.5*inch])
                        port_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 8),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecf0f1')]),
                            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ]))
                        
                        self.story.append(port_table)
                    else:
                        self.story.append(Paragraph("No open ports detected", self.styles['Normal']))
                    
                    self.story.append(Spacer(1, 0.2*inch))
            
            self.story.append(Spacer(1, 0.3*inch))
        
        self.story.append(PageBreak())
    
    def _add_vulnerabilities_section(self):
        """Add vulnerabilities section"""
        self.story.append(Paragraph("Vulnerabilities", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        vulnerabilities = self.db.get_vulnerabilities()
        
        if not vulnerabilities:
            self.story.append(Paragraph("No vulnerabilities found.", self.styles['Normal']))
            self.story.append(PageBreak())
            return
        
        # Group by severity
        by_severity = {'critical': [], 'high': [], 'medium': [], 'low': []}
        for vuln in vulnerabilities:
            severity = vuln.get('severity', 'low')
            by_severity[severity].append(vuln)
        
        # Add each severity level
        for severity in ['critical', 'high', 'medium', 'low']:
            vulns = by_severity[severity]
            if not vulns:
                continue
            
            self.story.append(Paragraph(
                f"{severity.upper()} Severity ({len(vulns)})",
                self.styles['SubsectionHeader']
            ))
            
            style_name = f"{severity.capitalize()}Alert"
            
            for vuln in vulns[:20]:  # Limit to 20 per severity
                host = vuln.get('host', 'Unknown')
                service = vuln.get('service', 'Unknown')
                vuln_type = vuln.get('vuln_type', 'Unknown')
                description = vuln.get('description', 'No description')
                
                vuln_text = f"• <b>{host}</b> ({service}) - {vuln_type}: {description}"
                self.story.append(Paragraph(vuln_text, self.styles[style_name]))
            
            self.story.append(Spacer(1, 0.2*inch))
        
        self.story.append(PageBreak())
    
    def _add_recommendations_section(self):
        """Add security recommendations section"""
        self.story.append(Paragraph("Security Recommendations", self.styles['SectionHeader']))
        self.story.append(Spacer(1, 0.2*inch))
        
        recommendations = [
            "Use WPA3 encryption for all WiFi networks where supported",
            "Implement strong, unique passwords (minimum 16 characters)",
            "Disable WPS (WiFi Protected Setup) on all access points",
            "Enable network segmentation to isolate critical systems",
            "Regularly update firmware on all network devices",
            "Implement MAC address filtering as an additional security layer",
            "Use a firewall and intrusion detection system",
            "Disable unnecessary services and close unused ports",
            "Implement regular security audits and penetration testing",
            "Enable logging and monitoring for suspicious activity"
        ]
        
        for rec in recommendations:
            self.story.append(Paragraph(f"• {rec}", self.styles['Normal']))
            self.story.append(Spacer(1, 0.1*inch))
        
        self.story.append(Spacer(1, 0.3*inch))
        
        # Footer
        footer = Paragraph(
            "<i>End of Report - Generated by PenDonn</i>",
            self.styles['Normal']
        )
        self.story.append(footer)

def generate_pdf_report(db, output_path=None, include_sections=None):
    """
    Generate PDF report
    
    Args:
        db: Database instance
        output_path: Path to save PDF (optional)
        include_sections: List of sections to include (optional)
    
    Returns:
        str: Path to generated PDF
    """
    report = PDFReport(db, output_path)
    return report.generate_report(include_sections)
