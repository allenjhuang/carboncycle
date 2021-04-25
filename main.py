import urllib
from datetime import datetime

import panel as pn
import googlemaps
from pint import UnitRegistry

pn.extension(css_files=["theme.css"])
pn.Accordion.margin = (0, -4)
pn.config.sizing_mode = "stretch_width"
pn.config.align = "center"

with open(".secrets", "r") as f:
    GMAP_API_KEY = f.read()
GMAP_FMT = (
    "https://www.google.com/maps/embed/v1/directions?mode=driving&key={key}&{query}"
)
DAYS_OF_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
HOURS_OF_DAY = [
    f"{hh:02d}:{mm:02d} {ap}"
    for ap in ["AM", "PM"]
    for hh in [12] + list(range(1, 12))
    for mm in range(0, 60, 15)
]
CO2_PER_GALLON = 19.60  # in pounds
EFFICIENCY_UNITS = {
    "mpg (US)": "miles per gallon",
    "mpg (imp)": "miles per imperial_gallon",
    "km/L": "kilometers per liter",
    "L/100 km": "100 * kilometers per liter",  # note, we must divide this by the fuel economy
}

IDLING_EFFICIENCY_UNITS = {
    "gal/hr (US)": "gallon per hour",
    "gal/hr (imp)": "imperial_gallon per hour",
    "L/hr": "liter per hour",
}


class CarbonCycle:
    def __init__(self):
        self.ureg = UnitRegistry()
        self.gmap = googlemaps.Client(key=GMAP_API_KEY)
        self.interactive_widget_list = []

    def _populate_sidebar(self):
        help_text = "<center>To get started, input both addresses!</center>"
        address_column = self._populate_address_column()
        car_column = self._populate_car_column()
        weekday_column = self._populate_weekday_column()
        sidebar_accordion = pn.Accordion(
            address_column, car_column, weekday_column, active=[0], toggle=True
        )
        self.dashboard.sidebar.append(help_text)
        self.dashboard.sidebar.append(sidebar_accordion)

    def _populate_address_column(self):
        self.home_widget = pn.widgets.TextInput(
            value="Natural History Building, Urbana, IL", placeholder="Home address"
        )
        self.work_widget = pn.widgets.TextInput(
            value="Natural Resources Building, Urbana, IL", placeholder="Work address"
        )
        self.interactive_widget_list.extend([
            self.home_widget,
            self.work_widget
        ])
        address_column = pn.Column(
            self.home_widget,
            self.work_widget,
            name="ADDRESSES",
        )
        return address_column

    def _populate_weekday_column(self):
        work_list = []
        self.leave_home_widgets = []
        self.leave_work_widgets = []
        for day in DAYS_OF_WEEK:
            need_commute_widget = pn.widgets.Checkbox(
                name=" Need to commute", value=not day.startswith("S")
            )
            leave_home_widget = pn.widgets.DiscreteSlider(
                name="Leave home at", options=HOURS_OF_DAY, value="08:00 AM"
            )
            self.leave_home_widgets.append(leave_home_widget)

            leave_work_widget = pn.widgets.DiscreteSlider(
                name="Leave work at",
                options=HOURS_OF_DAY,
                value="05:30 PM",
            )
            self.leave_work_widgets.append(leave_work_widget)

            work_column = pn.Column(
                need_commute_widget, leave_home_widget, leave_work_widget, name=day
            )
            work_list.append(work_column)
        weekday_accordion = pn.Accordion(*work_list, toggle=True)

        self.match_hour_widget = pn.widgets.Checkbox(name=" Match commute hours", value=True)
        weekday_column = pn.Column(
            weekday_accordion,
            self.match_hour_widget,
            name="TYPICAL WEEK",
        )
        return weekday_column

    def _populate_car_column(self):
        self.efficiency_widget = pn.widgets.FloatInput(
            name="Fuel economy", value=25, step=0.1,
        )
        self.efficiency_units_widget = pn.widgets.Select(
            options=list(EFFICIENCY_UNITS.keys())
        )
        self.idling_efficiency_widget = pn.widgets.FloatInput(
            name="Idling fuel usage", value=0.3, step=0.01,
        )
        self.idling_efficiency_units_widget = pn.widgets.Select(
            options=list(IDLING_EFFICIENCY_UNITS.keys())
        )
        self.interactive_widget_list.extend([
            self.efficiency_widget,
            self.efficiency_units_widget,
            self.idling_efficiency_widget,
            self.idling_efficiency_units_widget,
        ])
        car_column = pn.Column(
            self.efficiency_widget,
            self.efficiency_units_widget,
            self.idling_efficiency_widget,
            self.idling_efficiency_units_widget,
            name="AUTOMOBILE",
        )
        return car_column

    def _populate_main(self):
        self.map_html = pn.pane.HTML(height=500, margin=(10, 100))
        self.emission_summary = pn.pane.HTML(style={"text-align": "center"}, margin=(10, 100))
        main_row = pn.Row(self.map_html, self.emission_summary)
        self.dashboard.main.extend(main_row)

    @staticmethod
    def _format_map(origin, destination):
        map_query = urllib.parse.urlencode(
            {
                "origin": origin,
                "destination": destination,
                "waypoints": "|".join([origin, destination]),
            }
        )
        map_base_url = GMAP_FMT.format(key=GMAP_API_KEY, query=map_query)
        map_iframe = (
            f'<iframe width="100%" height="100%" src="{map_base_url}"> '
            f'frameborder="0" scrolling="no" marginheight="0" marginwidth="0"> '
            f"</iframe> "
        )
        return map_iframe

    def _call_gmap(self, origin, destination):
        response = self.gmap.distance_matrix(
            origins=origin,
            destinations=destination,
            mode="driving",
            language="English",
            departure_time=datetime.now(),
        )
        element = response["rows"][0]["elements"][0]
        distance = element["distance"]["value"] * self.ureg.meters
        idle_time = element["duration_in_traffic"]["value"] * self.ureg.seconds
        return distance, idle_time

    def _calculate_emissions(self, distance, idle_time, efficiency, idling_efficiency):

        travel_gallons_used = distance.to(self.ureg.miles) / efficiency.to(
            self.ureg.miles / self.ureg.gallons
        )
        idle_gallons_used = idle_time.to(self.ureg.hours) * idling_efficiency.to(
            self.ureg.gallons / self.ureg.hours
        )
        emissions = (travel_gallons_used + idle_gallons_used) * (
            CO2_PER_GALLON * self.ureg.pounds / self.ureg.gallons
        )
        return emissions

    def _format_summary(self, origin, destination, distance, efficiency, emissions):
        str_efficiency_units = efficiency.units if self.efficiency_units_widget.value != "L/100 km" else "liter / 100 kilometer"
        return f"""
            <div>
                It's about {distance.to(self.ureg.miles):.2fP} from {origin} (A) to {destination} (B)!
            </div>
            <div style="margin-top: 20px;">
                At {efficiency.magnitude:.0f} {str_efficiency_units}...
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE-WAY TRIP</strong><br>
                {emissions:~.2fP} of CO2
            </div>
            <div style="margin-top: 10px;">
                <strong>ROUND TRIP</strong><br>
                {2 * emissions:~.2fP} of CO2
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE WEEK (7 DAYS)</strong><br>
                {7 * 2 * emissions:~.2fP} of CO2
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE MONTH (30 DAYS)</strong><br>
                {30 * 2 * emissions:~.2fP} of CO2
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE YEAR (365 DAYS)</strong><br>
                {365 * emissions:~.2fP} of CO2
            </div>
            <div style="margin-top: 20px; font-size: 12px;">
                Did you know that a mature tree absorbs about 22 kilograms of carbon dioxide a year from the atmosphere? <sup>1</sup>
            </div>
            <div style="margin-top: 20px; font-size: 12px;">
Our CO2 emissions formula: 19.60 * (distance / fuel_economy + idle_time * idling_fuel_usage)<br>
19.60 pounds of CO2 are produced per gallon of gasoline. <sup>2</sup><br>
Idle time in traffic consumes fuel as well! <sup>3</sup> <sup>4</sup>
<br><br>
<sup>2</sup>Source: https://www.eia.gov/environment/emissions/co2_vol_mass.php<br>
<sup>3</sup>Source: https://www.energy.gov/eere/vehicles/fact-861-february-23-2015-idle-fuel-consumption-selected-gasoline-and-diesel-vehicles<br>
<sup>4</sup>Source: https://www.anl.gov/sites/www/files/2018-02/idling_worksheet.pdf
            </div>
        """

    def _add_interactivity(self):
        for widget in self.interactive_widget_list:
            if isinstance(widget, pn.widgets.DiscreteSlider):
                widget.param.watch(self._trigger_update, "value_throttled")
            else:
                widget.param.watch(self._trigger_update, "value")
        widget.param.trigger("value")
        self.match_hour_widget.param.watch(self._link_weekday_widgets, "value")
        self.match_hour_widget.param.trigger("value")

    def _trigger_update(self, event):
        origin = self.home_widget.value
        destination = self.work_widget.value

        efficiency_units = EFFICIENCY_UNITS[self.efficiency_units_widget.value]
        efficiency = self.efficiency_widget.value * self.ureg(efficiency_units)
        if self.efficiency_units_widget.value == "L/100 km":
            efficiency = self.ureg(efficiency_units) / self.efficiency_widget.value
        idling_efficiency_units = IDLING_EFFICIENCY_UNITS[self.idling_efficiency_units_widget.value]
        idling_efficiency = self.idling_efficiency_widget.value * self.ureg(idling_efficiency_units)

        self.map_html.object = self._format_map(origin, destination)
        distance, idle_time = self._call_gmap(origin, destination)
        emissions = self._calculate_emissions(distance, idle_time, efficiency, idling_efficiency)
        self.emission_summary.object = self._format_summary(
            origin, destination, distance, efficiency, emissions
        )

    def _link_weekday_widgets(self, event):
        if event.new:
            self.leave_home_links = [
                self.leave_home_widgets[0].link(
                    widget, value="value", bidirectional=True
                )
                for widget in self.leave_home_widgets[1:]
            ]
            self.leave_home_widgets[0].param.trigger()

            self.leave_work_links = [
                self.leave_work_widgets[0].link(
                    widget, value="value", bidirectional=True
                )
                for widget in self.leave_work_widgets[1:]
            ]
            self.leave_work_widgets[0].param.trigger()
        else:
            for link in self.leave_home_links:
                self.leave_home_widgets[0].param.unwatch(link)

            for link in self.leave_work_links:
                self.leave_work_widgets[0].param.unwatch(link)

    def view(self):
        self.dashboard = pn.template.MaterialTemplate(title="CARboncycle")
        self._populate_sidebar()
        self._populate_main()
        self._add_interactivity()
        self.dashboard.servable()


carbon_cycle = CarbonCycle()
carbon_cycle.view()
