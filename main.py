import os
import pickle
import urllib
from datetime import datetime, timedelta

import panel as pn
import googlemaps
from pint import UnitRegistry

pn.extension(css_files=["theme.css"])
pn.Accordion.margin = (0, -4)
pn.config.sizing_mode = "stretch_width"
pn.config.align = "center"

THIS_FP = os.path.dirname(os.path.realpath(__file__))
SECRETS_FP = os.path.join(THIS_FP, ".secrets")
CACHED_FP = os.path.join(THIS_FP, "locs.pkl")
with open(SECRETS_FP, "r") as f:
    GMAP_API_KEY = f.read()
GMAP_FMT = (
    "https://www.google.com/maps/embed/v1/directions?mode=driving&key={key}&{query}"
)
DAYS_OF_WEEK = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6
}
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

        self.locs = {}
        if os.path.exists(CACHED_FP):
            with open(CACHED_FP, "rb") as f:
                self.locs.update(pickle.load(f))

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
        self.need_commute_widgets = []
        self.leave_home_widgets = []
        self.leave_work_widgets = []
        for day in DAYS_OF_WEEK.keys():
            need_commute_widget = pn.widgets.Checkbox(
                name=f" Need to commute on {day}", value=not day.startswith("S")
            )
            self.need_commute_widgets.append(need_commute_widget)

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
            self.interactive_widget_list.extend([
                need_commute_widget,
                leave_home_widget,
                leave_work_widget
            ])

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
        self.map_html = pn.pane.HTML(height=450, margin=(10, 100))
        self.emission_summary = pn.pane.HTML(style={"text-align": "center"}, margin=(10, 125), min_width=300)
        self.weekday_summary = pn.pane.Markdown(style={"text-align": "center"}, max_width=215, sizing_mode='fixed', margin=(10, 125, 10, 0))
        main_row = pn.Column(self.map_html, pn.Row(self.emission_summary, self.weekday_summary))
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

    def _call_gmap(self, dt, origin, destination):
        print(dt)
        response = self.gmap.distance_matrix(
            origins=origin,
            destinations=destination,
            mode="driving",
            language="English",
            departure_time=dt,
        )
        element = response["rows"][0]["elements"][0]
        distance = element["distance"]["value"]
        idle_time = element.get("duration_in_traffic", {"value": 0})["value"]
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

    def _format_summary(self, origin, destination, distance, efficiency, dt_emissions):
        num_days = int(len(dt_emissions) / 2)
        week_emissions = sum(dt_emissions.values())
        one_way_emissions = week_emissions / num_days / 2
        round_trip_emissions = one_way_emissions * 2
        month_emissions = 4 * week_emissions
        year_emissions = 52 * week_emissions

        co2_absorbed = (22 * self.ureg.kilogram)
        if self.efficiency_units_widget.value == "mpg (US)":
            distance_units = self.ureg.miles
            co2_absorbed = co2_absorbed.to("lb")
            co2_per_gallon = CO2_PER_GALLON * self.ureg.lb
        else:
            distance_units = self.ureg.km
            co2_per_gallon = (CO2_PER_GALLON * self.ureg.lb).to("kg")
        str_distance = f"{distance.to(distance_units):.2fP}"
        str_efficiency_units = efficiency.units if self.efficiency_units_widget.value != "L/100 km" else "liter / 100 kilometer"

        weekday_summary = """<br><br>Day | <br><br>Time | <br><br>Traffic\n-------- | -------- | --------\n"""
        for i, day_label in enumerate(dt_emissions):
            distance, idle_time = self.locs[self.loc_label][day_label]
            distance = (distance * self.ureg("meter")).to("miles")
            idle_time = (idle_time * self.ureg("seconds")).to("minutes")
            day, time = day_label.split(' ', maxsplit=1)
            if i % 2 == 0:
                row_text = f"**{day}** | **{time}** | **{idle_time:~.2fP}**\n"
            else:
                row_text = f"{day} | {time} | {idle_time:~.2fP}\n"
            weekday_summary += row_text
        self.weekday_summary.object = weekday_summary

        self.emission_summary.object = f"""
            <div>
                <h3>It's about {str_distance}s from {origin} to {destination}!</h3>
            </div>
            <div style="margin-top: 20px;">
                If your automobile runs at {efficiency.magnitude:.0f} {str_efficiency_units}:
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE-WAY TRIP AVERAGES</strong><br>
                {one_way_emissions:~.2fP} of CO<sub>2</sub>
            </div>
            <div style="margin-top: 10px;">
                <strong>ROUND TRIP AVERAGES</strong><br>
                {round_trip_emissions:~.2fP} of CO<sub>2</sub>
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE WEEK OF TRIPS TO WORK ({num_days} DAYS) AVERAGES</strong><br>
                {week_emissions:~.2fP} of CO<sub>2</sub>
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE MONTH OF TRIPS TO WORK ({num_days * 4} DAYS) AVERAGES</strong><br>
                {month_emissions:~.2fP} of CO<sub>2</sub>
            </div>
            <div style="margin-top: 10px;">
                <strong>ONE YEAR OF TRIPS TO WORK ({num_days * 52} DAYS) AVERAGES</strong><br>
                {year_emissions:~.2fP} of CO<sub>2</sub>
            </div>
            <div style="margin-top: 20px; font-size: 12px;">
                Did you know that a mature tree absorbs about {co2_absorbed:~.2fP} of carbon dioxide a year from the atmosphere?
                <sup><a href="https://www.eea.europa.eu/articles/forests-health-and-climate-change/key-facts/trees-help-tackle-climate-change" target="_blank">1</a></sup>
            </div>
            <div style="margin-top: 20px; font-size: 12px;">

            Our CO<sub>2</sub> emissions formula: {co2_per_gallon.magnitude:.2f} * (distance / fuel_economy + time_in_traffic * idling_fuel_usage)<br>

            {co2_per_gallon:~.2fP} of CO<sub>2</sub> are produced per gallon of gasoline.
            <sup><a href="https://www.eia.gov/environment/emissions/co2_vol_mass.php" target="_blank">2</a></sup><br>

            Idle time in traffic consumes fuel as well!
            <sup><a href="https://www.energy.gov/eere/vehicles/fact-861-february-23-2015-idle-fuel-consumption-selected-gasoline-and-diesel-vehicles">3</a></sup>
            <sup><a href="https://www.anl.gov/sites/www/files/2018-02/idling_worksheet.pdf" target="_blank">4</a></sup>
        """

    def _add_interactivity(self):
        for widget in self.interactive_widget_list:
            if isinstance(widget, pn.widgets.DiscreteSlider):
                widget.param.watch(self._trigger_update, "value_throttled")
            else:
                widget.param.watch(self._trigger_update, "value")
        self.interactive_widget_list[0].param.trigger("value")
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

        dt_emissions = {}
        self.loc_label = f"{self.home_widget.value} {self.work_widget.value}"
        if self.loc_label not in self.locs:
            self.locs[self.loc_label] = {}

        for widgets in zip(self.need_commute_widgets, self.leave_home_widgets, self.leave_work_widgets):
            need_commute_widget, leave_home_widget, leave_work_widget = widgets
            if not need_commute_widget.value:
                continue
            day_of_week = need_commute_widget.name.split(" ")[-1]
            for time in [leave_home_widget.value, leave_work_widget.value]:
                dt = self._get_dt(day_of_week, time)
                day_label = dt.strftime("%a %I:%M %p")

                if day_label in self.locs[self.loc_label]:
                    distance, idle_time = self.locs[self.loc_label][day_label]
                else:
                    distance, idle_time = self._call_gmap(dt, origin, destination)
                    self.locs[self.loc_label][day_label] = distance, idle_time
                distance = distance * self.ureg.meters
                idle_time = idle_time * self.ureg.seconds
                emissions = self._calculate_emissions(distance, idle_time, efficiency, idling_efficiency)
                dt_emissions[day_label] = emissions

        if not os.path.exists(CACHED_FP):
            with open(CACHED_FP, "wb") as f:
                pickle.dump(self.locs, f)

        self._format_summary(
            origin, destination, distance, efficiency, dt_emissions
        )

    def _get_dt(self, day_of_week, time):
        time, apm = time.split(" ")
        hour, minute = map(int, time.split(":")[:2])
        if apm == "PM":
            hour += 12
            if hour > 23:
                hour -= 24
        now = datetime.today().replace(second=0, microsecond=0)
        tomorrow = now + timedelta(days=1)
        dt = self._next_weekday(
            tomorrow, DAYS_OF_WEEK[day_of_week]
        ).replace(hour=hour, minute=minute)
        return dt

    @staticmethod
    def _next_weekday(dt, weekday):
        days_ahead = weekday - dt.weekday()
        if days_ahead <= 0: # Target day already happened this week
            days_ahead += 7
        return dt + timedelta(days_ahead)

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
