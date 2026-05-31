#!/Applications/QGIS.app/Contents/MacOS/python

import argparse
import os
from pathlib import Path

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.core import (
    QgsApplication,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMapRendererCustomPainterJob,
    QgsMapSettings,
    QgsProject,
    QgsRectangle,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)


ROOT = Path(__file__).resolve().parent
WORLD_PATH = ROOT / "world_map.gpkg"
AFRICA_EXTENT = QgsRectangle(-19.24, -36.63, 52.70, 39.14)
AFRICA_ISO_A3 = [
    "DZA",
    "AGO",
    "BEN",
    "BWA",
    "BFA",
    "BDI",
    "CPV",
    "CMR",
    "CAF",
    "TCD",
    "COM",
    "COG",
    "COD",
    "CIV",
    "DJI",
    "EGY",
    "GNQ",
    "ERI",
    "SWZ",
    "ETH",
    "GAB",
    "GMB",
    "GHA",
    "GIN",
    "GNB",
    "KEN",
    "LSO",
    "LBR",
    "LBY",
    "MDG",
    "MWI",
    "MLI",
    "MRT",
    "MUS",
    "MAR",
    "MOZ",
    "NAM",
    "NER",
    "NGA",
    "RWA",
    "STP",
    "SEN",
    "SYC",
    "SLE",
    "SOM",
    "ZAF",
    "SSD",
    "SDN",
    "TZA",
    "TGO",
    "TUN",
    "UGA",
    "ESH",
    "ZMB",
    "ZWE",
]

TIER_SPECS = [
    {"label": "Priority 1", "upper_share": 0.01, "color": "#701813", "width_mm": 0.46, "opacity": 1.00},
    {"label": "Priority 2", "upper_share": 0.05, "color": "#9b2d25", "width_mm": 0.38, "opacity": 0.95},
    {"label": "Priority 3", "upper_share": 0.20, "color": "#c8594d", "width_mm": 0.30, "opacity": 0.85},
    {"label": "Priority 4", "upper_share": 0.50, "color": "#e39a91", "width_mm": 0.24, "opacity": 0.76},
    {"label": "Priority 5", "upper_share": 1.00, "color": "#f5d8d4", "width_mm": 0.19, "opacity": 0.72},
]


def styled_countries() -> QgsVectorLayer:
    layer = QgsVectorLayer(f"{WORLD_PATH}|layername=countries", "countries", "ogr")
    if not layer.isValid():
        raise RuntimeError("Failed to load world map")

    iso_list = ", ".join(f"'{code}'" for code in AFRICA_ISO_A3)
    layer.setSubsetString(f"\"ISO_A3\" IN ({iso_list})")

    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#f7f6f1",
            "outline_color": "#b8b8b2",
            "outline_width": "0.13",
            "outline_width_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return layer


def make_line_symbol(color: str, width_mm: float) -> QgsLineSymbol:
    return QgsLineSymbol.createSimple(
        {
            "line_color": color,
            "line_width": str(width_mm),
            "line_width_unit": "MM",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )


def make_roads_layer(data_path: Path, name: str, subset: str, color: str, width_mm: float, opacity: float) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"{data_path}|layername=bottleneck_roads", name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Failed to load roads layer from {data_path}")

    if subset:
        layer.setSubsetString(subset)
    layer.setRenderer(QgsSingleSymbolRenderer(make_line_symbol(color, width_mm)))
    layer.setOpacity(opacity)
    return layer


def priority_layers(data_path: Path) -> list[QgsVectorLayer]:
    template = QgsVectorLayer(f"{data_path}|layername=bottleneck_roads", "template", "ogr")
    if not template.isValid():
        raise RuntimeError(f"Failed to load roads layer from {data_path}")

    n_features = template.featureCount()
    if n_features <= 0:
        raise RuntimeError("The bottleneck roads layer is empty")

    layers: list[QgsVectorLayer] = []
    lower_rank = 1
    for idx, spec in enumerate(TIER_SPECS, start=1):
        upper_rank = max(lower_rank, int(n_features * spec["upper_share"]))
        subset = f"\"NI_rank\" >= {lower_rank} AND \"NI_rank\" <= {upper_rank}"
        layer = make_roads_layer(
            data_path=data_path,
            name=f"priority_{idx}",
            subset=subset,
            color=spec["color"],
            width_mm=spec["width_mm"],
            opacity=spec["opacity"],
        )
        layers.append(layer)
        lower_rank = upper_rank + 1

    base_layer = make_roads_layer(
        data_path=data_path,
        name="priority_base",
        subset="",
        color="#d7d3cf",
        width_mm=0.14,
        opacity=0.32,
    )
    layers.append(base_layer)
    return layers


def render_panel(data_path: Path, output: Path, width: int, height: int, dpi: int) -> None:
    countries = styled_countries()
    roads = priority_layers(data_path)
    layers = roads + [countries]

    project = QgsProject.instance()
    for layer in layers:
        project.addMapLayer(layer, False)

    settings = QgsMapSettings()
    settings.setBackgroundColor(QColor("white"))
    settings.setLayers(layers)
    settings.setExtent(AFRICA_EXTENT)
    settings.setOutputSize(QSize(width, height))
    settings.setOutputDpi(dpi)
    settings.setFlag(QgsMapSettings.Antialiasing, True)
    settings.setFlag(QgsMapSettings.UseAdvancedEffects, True)

    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start()
    job.waitForFinished()
    painter.end()

    if not image.save(str(output)):
        raise RuntimeError(f"Failed to save {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PROJ_LIB", "/Applications/QGIS.app/Contents/Resources/qgis/proj")
    os.environ.setdefault("PROJ_DATA", "/Applications/QGIS.app/Contents/Resources/qgis/proj")

    QgsApplication.setPrefixPath("/Applications/QGIS.app/Contents/MacOS", True)
    app = QgsApplication([], False)
    app.initQgis()
    render_panel(Path(args.data), Path(args.output), args.width, args.height, args.dpi)
    os._exit(0)


if __name__ == "__main__":
    main()
