from __future__ import annotations

from pathlib import Path

from .base import XsdSpecPdfConfig, XsdSpecPdfParser


PROFILE_NAME = "mx-cfdi-anexo20-2022"

PARSER = XsdSpecPdfParser(
    XsdSpecPdfConfig(
        profile_name=PROFILE_NAME,
        start_element_name="Comprobante",
        root_path="/cfdi:Comprobante",
        element_path_overrides={
            "Comprobante#1": "/cfdi:Comprobante",
            "InformacionGlobal#1": "/cfdi:Comprobante/cfdi:InformacionGlobal",
            "CfdiRelacionados#1": "/cfdi:Comprobante/cfdi:CfdiRelacionados",
            "CfdiRelacionado#1": "/cfdi:Comprobante/cfdi:CfdiRelacionados/cfdi:CfdiRelacionado",
            "Emisor#1": "/cfdi:Comprobante/cfdi:Emisor",
            "Receptor#1": "/cfdi:Comprobante/cfdi:Receptor",
            "Conceptos#1": "/cfdi:Comprobante/cfdi:Conceptos",
            "Concepto#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto",
            "Impuestos#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Impuestos",
            "Traslados#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Impuestos/cfdi:Traslados",
            "Traslado#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado",
            "Retenciones#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Impuestos/cfdi:Retenciones",
            "Retencion#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion",
            "ACuentaTerceros#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:ACuentaTerceros",
            "InformacionAduanera#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:InformacionAduanera",
            "CuentaPredial#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:CuentaPredial",
            "ComplementoConcepto#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:ComplementoConcepto",
            "Parte#1": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Parte",
            "InformacionAduanera#2": "/cfdi:Comprobante/cfdi:Conceptos/cfdi:Concepto/cfdi:Parte/cfdi:InformacionAduanera",
            "Impuestos#2": "/cfdi:Comprobante/cfdi:Impuestos",
            "Retenciones#2": "/cfdi:Comprobante/cfdi:Impuestos/cfdi:Retenciones",
            "Retencion#2": "/cfdi:Comprobante/cfdi:Impuestos/cfdi:Retenciones/cfdi:Retencion",
            "Traslados#2": "/cfdi:Comprobante/cfdi:Impuestos/cfdi:Traslados",
            "Traslado#2": "/cfdi:Comprobante/cfdi:Impuestos/cfdi:Traslados/cfdi:Traslado",
            "Complemento#1": "/cfdi:Comprobante/cfdi:Complemento",
            "Addenda#1": "/cfdi:Comprobante/cfdi:Addenda",
        },
    )
)


def extract(pdf_path: Path) -> list[dict[str, object]]:
    return PARSER.extract(Path(pdf_path))
