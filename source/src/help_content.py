"""Centralised help content for Frog Mod Editor.

Each top-level key in HELP_TOPICS maps to one editor page. Each
page has an ordered list of sections. A section can be:

  {
    'id': 'unique-anchor',         # used by search + nav
    'title': 'Section Heading',
    'body': '<p>HTML content...</p>',
    'subsections': [ {...recursive...} ]
  }

Body is rich text (Qt's QTextBrowser HTML subset). Use <h3> for
inner headings, <code> for inline code, <pre> for blocks, <b> for
emphasis. Avoid heavy CSS; the dialog applies a global stylesheet.

The content here is verbose by design — Frog asked for "extremely
detailed and thorough" help. Sections are split fine-grained so the
search-by-title feature can land on the specific topic.
"""
from __future__ import annotations

from typing import Any, Dict, List


# ──────────────────────────────────────────────────────────────────────
# Reusable snippets
# ──────────────────────────────────────────────────────────────────────
_DISCLAIMER_HEURISTIC = (
    '<p style="color: #d9a13a;"><b>Heuristic note:</b> Motor Town’s '
    'underlying physics live in native C++ that we can’t read, so '
    'the editor’s estimates are derived from documented field '
    'semantics + observed vanilla behaviour. The relative effect of '
    'editing a field is reliable; absolute numeric predictions may '
    'differ slightly in-game.</p>'
)


# ──────────────────────────────────────────────────────────────────────
# Workspace (Generated Parts) — stack index 1
# ──────────────────────────────────────────────────────────────────────
_WORKSPACE = {
    'title': 'Generated Parts Workspace',
    'subtitle': 'Edit existing modded parts you\'ve already created.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The Generated Parts workspace is where you edit modded '
                'parts you’ve already created. The left sidebar lists '
                'every part Frog Mod Editor has generated; click one to '
                'load it into the editor on the right.</p>'
                '<p>For the original create flow (forking a vanilla part '
                'into a new modded one), use the <b>Engines</b> or '
                '<b>Tires</b> launcher buttons on the home screen.</p>'
            ),
        },
        {
            'id': 'editing',
            'title': 'Editing fields',
            'body': (
                '<p>Click any property field in the editor to change its '
                'value. As you type:</p>'
                '<ul>'
                '<li>The border turns <span style="color:#d9a13a">yellow</span> '
                'if the value is outside the typical range for that field '
                '(unusual, but allowed).</li>'
                '<li>The border turns <span style="color:#d44848">red</span> '
                'if the value is outside the safe range (saving will be '
                'blocked until you fix it).</li>'
                '</ul>'
                '<p>The grey text below each field shows the typical '
                'range plus a description of what the field does. Hover '
                'over the input to see both ranges in a tooltip.</p>'
            ),
        },
        {
            'id': 'saving',
            'title': 'Saving and backups',
            'body': (
                '<p>Click <b>Save</b> in the top bar to commit your '
                'edits. Each save creates two backup files:</p>'
                '<ul>'
                '<li>A persistent <code>.bak</code> in the editor’s '
                'backup directory — only created the first time you '
                'save; never overwritten. Use this to roll back a part '
                'all the way to its original generated state.</li>'
                '<li>A rolling <code>.current.bak</code> next to the '
                'live file — overwritten on every save. Use this '
                'to undo your most recent save.</li>'
                '</ul>'
                '<p>If validation fails after the write, both files are '
                'restored automatically and the save is reported as '
                'failed.</p>'
            ),
        },
        {
            'id': 'volume',
            'title': 'Engine: Volume Adjustment',
            'body': (
                '<p>Engines have a <b>Volume Adjustment</b> slider near '
                'the Sound Pack dropdown. Range -25 to +25, integer '
                'steps. Each step shifts the engine’s in-game audio '
                'output by 4%, so:</p>'
                '<ul>'
                '<li><b>0</b> = vanilla volume</li>'
                '<li><b>+10</b> = +40% (1.40×)</li>'
                '<li><b>+25</b> = +100% (2.0×)</li>'
                '<li><b>-25</b> = silent (0.0×)</li>'
                '</ul>'
                '<p>The slider value persists in the engine’s '
                '<code>.creation.json</code> sidecar and the editor '
                'auto-generates a UE4SS Lua mod (FrogModEngineVolume) '
                'that applies the multiplier in-game. UE4SS must be '
                'installed for the volume adjustment to take effect.</p>'
                '<p>Adjusting the slider on an existing engine and '
                'saving regenerates the Lua mod with the new value '
                '— no fork required.</p>'
            ),
        },
        {
            'id': 'delete',
            'title': 'Deleting a part',
            'body': (
                '<p>Use <b>File > Delete current part</b> (or right-click '
                'on the sidebar entry) to remove a generated part. '
                'Deletion removes:</p>'
                '<ul>'
                '<li>The <code>.uasset</code> + <code>.uexp</code> '
                'asset files</li>'
                '<li>The <code>.creation.json</code> sidecar</li>'
                '<li>Any matching rows from the Engines or VehicleParts0 '
                'DataTable</li>'
                '<li>The site_engines.json or site_tires.json registry '
                'entry</li>'
                '</ul>'
                '<p>The persistent <code>.bak</code> stays so you can '
                'recover the deleted part later if needed.</p>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Engine / Tire Creator — stack index 2
# ──────────────────────────────────────────────────────────────────────
_CREATOR_ENGINE_SECTIONS: List[Dict[str, Any]] = [
    {
        'id': 'engine-template',
        'title': 'Choosing a template engine',
        'body': (
            '<p>Every modded engine starts as a fork of a vanilla '
            '<i>donor</i> engine. The donor’s binary layout (which '
            'fields it exposes, how the torque curve is shaped, what '
            'sound pack and asset references it carries) becomes the '
            'starting point for your edits.</p>'
            '<p>The catalog on the left groups donors by cylinder family. '
            'Pick the donor whose layout best matches what you’re '
            'building — you can’t add fields the donor '
            'doesn’t have, but you can change every value.</p>'
            '<p>Notable donor properties:</p>'
            '<ul>'
            '<li><b>HeavyDuty_440HP</b> — default donor for new '
            'engines. Robust 16-property layout, includes most '
            'editable fields.</li>'
            '<li><b>Bike_*</b> — 14-property layout with StarterRPM. '
            'Use for motorcycle engines.</li>'
            '<li><b>Electric_*</b> — EV layout (~11 fields, '
            'no fuel/jake/intake). Forking an EV donor is required for '
            'electric engines because the binary slots differ.</li>'
            '</ul>'
        ),
    },
    {
        'id': 'engine-fields-performance',
        'title': 'Engine field reference: Performance',
        'body': (
            '<h3>MaxTorque</h3>'
            '<p>Peak crank torque in N·m. The single biggest factor '
            'in how powerful the engine feels. Vanilla range '
            '~12 N·m (Scooter 10HP) up to ~1,500 N·m '
            '(HeavyDuty 540HP). Typical car engines: 80–520 N·m. '
            'Editor warns above 2,000 N·m and blocks above '
            '50,000 N·m.</p>'
            '<h3>MaxRPM</h3>'
            '<p>Engine redline. Hard range 2,000–14,000 RPM '
            '(below 2,000 most engines break in-game; above 14,000 '
            'the simulation gets unstable). Typical 2,800–10,000. '
            'Note: vanilla EVs ship at 21,000 RPM, which exceeds the '
            'editor’s cap — forking an EV donor requires '
            'bringing MaxRPM down to ≤14,000 first.</p>'
            '<h3>TorqueCurve</h3>'
            '<p>Internal UE5 import reference (read-only). The negative '
            'number is a package index pointing to a separate torque-'
            'curve asset that shapes how torque is distributed across '
            'the RPM band. The curve determines the torque <i>shape</i> '
            '(peaky vs flat); MaxTorque sets the peak height.</p>'
            '<h3>Peak Torque RPM (creator-only)</h3>'
            '<p>The RPM where torque is highest. Synthetic field that '
            'reshapes the engine’s torque curve to peak at this '
            'point. See the cross-field validator section below for '
            'realistic ranges per engine class.</p>'
            '<h3>Max HP and Peak HP RPM (creator-only)</h3>'
            '<p>Target peak horsepower and the RPM where it occurs. '
            'The editor uses these to shape the falloff past peak '
            'torque so the curve actually delivers the requested HP. '
            'If MaxTorque is too small to physically produce the '
            'requested HP at the requested RPM, the curve preview '
            'caps at the achievable value and the status line tells '
            'you why.</p>'
        ),
    },
    {
        'id': 'engine-fields-friction',
        'title': 'Engine field reference: Friction & Fuel',
        'body': (
            '<h3>Inertia</h3>'
            '<p>Rotational inertia of the engine assembly (flywheel, '
            'crank). Controls how quickly the engine revs up and down '
            '— higher = slower response. Typical gas engines: '
            '1,200–5,200. Heavy diesels: up to 50,000.</p>'
            '<h3>FrictionCoulombCoeff</h3>'
            '<p>Constant mechanical drag from bearings, seals, baseline '
            'friction. Acts as a flat drag regardless of RPM. Typical '
            'gas engines: 180,000–500,000. Heavy diesels: up to '
            '2.5 million.</p>'
            '<h3>FrictionViscosityCoeff</h3>'
            '<p>RPM-dependent drag from oil shear, pumping losses, '
            'windage. Increases with engine speed — higher values '
            'punish high-RPM performance. Typical gas: 450–1,050. '
            'Bikes: 330–500. EVs: 100.</p>'
            '<h3>FuelConsumption</h3>'
            '<p>Base fuel-use scalar. Higher = more fuel consumed for '
            'a given power output. Vanilla 3 (scooter) up to 670 '
            '(EV 670HP — EVs use this for energy drain too).</p>'
        ),
    },
    {
        'id': 'engine-fields-start',
        'title': 'Engine field reference: Start, Idle, Pops',
        'body': (
            '<h3>StarterTorque</h3>'
            '<p>Torque the starter motor applies while cranking. '
            'Typical gas: 200,000. Heavy diesels: up to 3 million.</p>'
            '<h3>StarterRPM</h3>'
            '<p>Target RPM the starter tries to reach before the engine '
            'catches. Vanilla 1,500 on diesels and modern bikes. Must '
            'be lower than MaxRPM. Not present on every layout.</p>'
            '<h3>IdleThrottle</h3>'
            '<p>Minimum throttle that keeps the engine running at idle. '
            'Scale varies dramatically by layout: compact gas engines '
            '~0.002–0.005, modern bikes ~0.0002, diesels ~0.017. '
            '<b>Danger:</b> values above 1.0 on compact layouts cause '
            'the vehicle to creep forward without throttle input. The '
            'editor blocks anything above 1.0 to prevent this.</p>'
            '<h3>BlipThrottle</h3>'
            '<p>Throttle amount used for automatic rev-match blips '
            'during downshifts. Vanilla 1.0 (scooter) to 10.0 (V8s). '
            'Higher = more aggressive and audible.</p>'
            '<h3>BlipDurationSeconds</h3>'
            '<p>Duration of the rev-match blip. Vanilla 0.2–0.5s '
            'for gas engines, up to 3.0s for bikes.</p>'
            '<h3>HeatingPower</h3>'
            '<p>Explicit heat-generation term. Only present on some '
            'layouts (V8s, bikes). Vanilla bikes ~1.15–1.17. '
            'Affects engine temperature buildup.</p>'
            '<h3>AfterFireProbability</h3>'
            '<p>Decel pop / backfire probability scalar. Vanilla 1.0 '
            'on engines that have it (V8s, bikes). 0.0 = no pops, '
            '1.0 = frequent pops.</p>'
        ),
    },
    {
        'id': 'engine-fields-ev',
        'title': 'Engine field reference: EV-only',
        'body': (
            '<p>These fields appear only on EV donors. They’re '
            'hidden when Fuel Type is set to Gasoline or Diesel, and '
            'switching to Electric on a non-EV donor triggers a donor '
            'swap because the binary layouts differ.</p>'
            '<h3>MotorMaxPower</h3>'
            '<p>Peak motor output in kW. Vanilla 230 kW (Electric 130HP) '
            'to 505 kW (Electric 670HP). Primary power stat for EVs.</p>'
            '<h3>MotorMaxVoltage</h3>'
            '<p>Maximum system voltage in V. Vanilla 200–670V. '
            'Higher voltage generally pairs with higher power.</p>'
            '<h3>MotorMaxRPM</h3>'
            '<p>Motor speed ceiling for EV layouts that expose it. '
            'Caps motor rotational speed independently of MaxRPM. '
            'Note: the MaxRPM field has its own tighter cap of 14,000.</p>'
            '<h3>MaxRegenTorqueRatio</h3>'
            '<p>Regenerative braking strength. Vanilla 0.3 on all stock '
            'EVs. Higher = stronger regen. Editor warns above 1.0.</p>'
        ),
    },
    {
        'id': 'engine-fields-diesel',
        'title': 'Engine field reference: Diesel-only',
        'body': (
            '<h3>IntakeSpeedEfficiency</h3>'
            '<p>Diesel/heavy-duty airflow efficiency term '
            '(reverse-engineered). Vanilla 1.0 on all observed '
            'diesels. Safe range 0.5–2.0. Deviating far from '
            '1.0 may produce unpredictable power behaviour.</p>'
            '<h3>MaxJakeBrakeStep</h3>'
            '<p>Maximum jake-brake (engine brake) strength in discrete '
            'steps. Vanilla 3 on all observed heavy-duty diesels. '
            'Integer values only. Higher values allow stronger '
            'engine-braking.</p>'
            '<h3>EngineType</h3>'
            '<p>Diesel-specific engine classification enum stored as '
            'a raw integer. Vanilla 2 on heavy-duty diesels. The full '
            'enum mapping is only partially decoded — leave at '
            'the template default unless you know what you’re '
            'doing.</p>'
        ),
    },
    {
        'id': 'engine-rpm-validator',
        'title': 'Cross-field RPM curve validator',
        'body': (
            '<p>The editor cross-checks Peak Torque RPM, Peak HP RPM '
            'and MaxRPM against typical real-world engine curves. '
            'This catches cases where each field passes its own bounds '
            'but the trio is physically nonsensical (e.g. peak torque '
            'at 400 RPM on a 5,000 RPM redline).</p>'
            '<h3>Typical curve shapes by engine class:</h3>'
            '<table cellpadding="6" style="border-collapse: collapse;">'
            '<tr><th align="left">Engine class</th><th>Peak torque (% redline)</th><th>Peak HP (% redline)</th></tr>'
            '<tr><td>NA petrol</td><td>50–75%</td><td>80–95%</td></tr>'
            '<tr><td>Turbo petrol</td><td>30–50%</td><td>75–90%</td></tr>'
            '<tr><td>NA diesel</td><td>40–60%</td><td>75–90%</td></tr>'
            '<tr><td>Turbo diesel (HD)</td><td>25–40%</td><td>60–80%</td></tr>'
            '<tr><td>Sport bike</td><td>60–80%</td><td>80–95%</td></tr>'
            '<tr><td>Electric motor</td><td>0% (instant)</td><td>30–60%</td></tr>'
            '</table>'
            '<h3>Editor enforcement (ICE only):</h3>'
            '<ul>'
            '<li><b>Peak Torque RPM</b> as % of MaxRPM: typical '
            '25–90%, hard 10–100%</li>'
            '<li><b>Peak HP RPM</b> as % of MaxRPM: typical '
            '60–100%, hard 30–100%</li>'
            '<li><b>Inverted curve</b> (peak HP RPM &lt; peak torque '
            'RPM): warning, very rare on real engines</li>'
            '</ul>'
            '<p>EV engines bypass these checks entirely — electric '
            'motors don’t follow ICE curve conventions.</p>'
        ),
    },
    {
        'id': 'engine-curve-preview',
        'title': 'Live torque/HP curve preview',
        'body': (
            '<p>The "Curve Preview" card under the property cards shows '
            'a live torque + HP chart that updates as you type. Two '
            'series:</p>'
            '<ul>'
            '<li><span style="color:#73c686"><b>Torque (Nm)</b></span> on the left axis</li>'
            '<li><span style="color:#5fa9d9"><b>HP</b></span> on the right axis</li>'
            '</ul>'
            '<p>Curve shape is parametric (4-segment piecewise: idle '
            'rise → plateau → peak HP region → redline '
            'falloff) so the lines are always smooth. The status line '
            'below the chart shows the headline numbers.</p>'
            '<p>If you set a Max HP that’s impossible to achieve '
            'with your MaxTorque (e.g. 200 HP on 110 Nm at 11,000 RPM '
            'requires more torque than you have), the curve honestly '
            'shows the achievable peak and the status line tells you '
            'how to fix it.</p>'
        ),
    },
    {
        'id': 'engine-level-requirements',
        'title': 'Engine Unlock Requirements',
        'body': (
            '<p>Restrict who can buy the engine in-game by character '
            'class + level. Click <b>+ Add condition</b> to add rules '
            'like "Truck level 5" or "Racer level 12". Multiple '
            'conditions are AND-ed (the player must meet ALL of them).</p>'
            '<p>Tick <b>Unlock by default</b> to skip all requirements '
            '(engine is available to any character at level 1).</p>'
            '<p>Implementation note: this writes to '
            '<code>LevelRequirementToBuy</code> on the engine’s '
            'DataTable row — a TMap of '
            '<code>EMTCharacterLevelType</code> to int level. Both '
            'populated and empty donors are supported (the editor uses '
            'a two-stage byte locator to find the field in the row '
            'tail).</p>'
        ),
    },
    {
        'id': 'engine-fuel-type',
        'title': 'Fuel Type and donor swaps',
        'body': (
            '<p>The Fuel Type dropdown controls which property fields '
            'are visible in the form:</p>'
            '<ul>'
            '<li><b>Gasoline</b> — ICE fields visible '
            '(Starter, Idle, Blip, AfterFire). EV fields hidden.</li>'
            '<li><b>Diesel</b> — same as Gasoline plus '
            'Diesel-only fields (IntakeSpeedEfficiency, MaxJakeBrakeStep).</li>'
            '<li><b>Electric</b> — EV fields visible '
            '(MotorMaxPower, MotorMaxVoltage, MaxRegenTorqueRatio). '
            'ICE/Diesel fields hidden.</li>'
            '</ul>'
            '<p>Switching between Gasoline and Diesel is free — they '
            'use the same binary layout. Switching to/from Electric '
            'requires a donor swap because the binary slots differ. '
            'The editor will prompt for confirmation and offer to '
            'reload from a sensible default donor (e.g. Electric_300HP).</p>'
        ),
    },
]


_CREATOR_TIRE_SECTIONS: List[Dict[str, Any]] = [
    {
        'id': 'tire-template',
        'title': 'Choosing a tire template',
        'body': (
            '<p>Tire templates are vanilla tire assets you fork into '
            'a new modded tire. The catalog groups them by use case '
            '(Street, Performance, Off-road, Heavy-Duty, Heavy '
            'Machine, Motorcycle).</p>'
            '<p>Important: vanilla tires expose different field sets '
            'depending on which "layout" they use. The editor only '
            'shows fields that are actually serialized for your chosen '
            'donor (e.g. TreadDepth and TireTemperature appear only on '
            'the 14-float layout). Hidden = field not present in this '
            'binary, not "missing data".</p>'
        ),
    },
    {
        'id': 'tire-vehicle-classes',
        'title': 'Vehicle Compatibility',
        'body': (
            '<p>Tick every vehicle class the tire should appear on in '
            'the in-game modification list. The server registers ONE '
            'row in the VehicleParts0 DataTable per ticked class '
            '(same FName, distinct fname_number).</p>'
            '<p>Why multi-select? Vanilla MT stores one row per '
            '(tire, vehicle_class) pair. The previous one-row design '
            'cloned only one donor, so a modded tire only appeared on '
            'whatever vehicle class that single donor matched — '
            'giving the impression that "modded tires don’t show '
            'up" everywhere else.</p>'
            '<p>Available classes:</p>'
            '<ul>'
            '<li>Car (Standard / Performance / Drift / Off-road)</li>'
            '<li>Motorcycle</li>'
            '<li>Heavy-Duty Truck (Front / Rear)</li>'
            '<li>Heavy Machine (Front / Rear)</li>'
            '</ul>'
            '<p>Each class has its own donor row whose '
            '<code>VehicleKeys</code> / <code>TruckClasses</code> / '
            '<code>VehicleTypes</code> filter fields control which '
            'in-game vehicles see the tire as an option.</p>'
        ),
    },
    {
        'id': 'tire-grip-formula',
        'title': 'How estimated grip is calculated',
        'body': (
            '<p>The editor estimates two grip values:</p>'
            '<pre>Street  G  =  Cornering Stiffness  +  (Camber Stiffness ÷ 2)\n'
            'Offroad G  =  Street G  ×  (1  +  GripMultiplier ÷ 100)</pre>'
            '<p><b>Why Camber is half-weighted:</b> the camber bonus '
            'only kicks in when the wheel is actively cambered into a '
            'corner. A flat-out grip estimate splits the difference '
            'between "no camber" and "full camber".</p>'
            '<p><b>Tires without Camber Stiffness on their layout</b> '
            'treat it as 0, so the estimate becomes just the cornering '
            'value.</p>'
            '<p><b>Worked example:</b><br>'
            'Cornering = 0.97, Camber = 0.30, GripMultiplier = +25</p>'
            '<pre>Street  = 0.97 + 0.30/2 = 1.12 G\n'
            'Offroad = 1.12 × 1.25     = 1.40 G</pre>'
            + _DISCLAIMER_HEURISTIC
        ),
    },
    {
        'id': 'tire-fields-grip',
        'title': 'Tire field reference: Grip & Slip',
        'body': (
            '<h3>LateralStiffness</h3>'
            '<p>How firm the sidewall is sideways. Higher = the tire '
            'deforms less when you turn the wheel — sharper '
            'response, less forgiving (sudden grip loss vs gradual '
            'slide). Stock cars 600–800k. Performance 900k+. '
            'Heavy-duty trucks need higher just to handle load.</p>'
            '<h3>LongStiffness</h3>'
            '<p>How firm the tire is under acceleration / braking. '
            'Higher = crisper throttle and brake response, but more '
            'prone to wheelspin or lockup. Stock cars 500–700k. '
            'Race tires 800k+.</p>'
            '<h3>LongSlipStiffness</h3>'
            '<p>How quickly the tire reacts when it starts to slip. '
            'Higher = slip catches up faster (better launches, more '
            'consistent ABS feel). Lower = slip develops more '
            'gradually. Stock cars 150–250k.</p>'
            '<h3>CorneringStiffness</h3>'
            '<p>Mid-corner grip — how much grip the tire has '
            'WHILE turning. Higher = more bite, carries more speed '
            'through bends. Above 1.2 feels glued; above 2.0 is '
            'arcade-grippy. Stock 0.85–1.05. Performance '
            '1.05–1.4. Drift tires drop this on purpose.</p>'
            '<h3>CamberStiffness</h3>'
            '<p>Extra cornering grip when the wheel is tilted '
            '(cambered) into the corner. Race cars run negative '
            'camber to take advantage. Half-weighted in the grip '
            'estimate.</p>'
            '<h3>GripMultiplier</h3>'
            '<p>Off-road grip boost as a percentage. 0 = stock, '
            '+50 = 50% more grip on dirt/sand/grass, -25 = 25% less. '
            'Affects loose surfaces; on tarmac the effect is small. '
            'Typical -50 to +100.</p>'
        ),
    },
    {
        'id': 'tire-fields-load',
        'title': 'Tire field reference: Load & Wear',
        'body': (
            '<h3>LoadRating and MaxLoad</h3>'
            '<p>Internal load-related scalars. The exact gameplay '
            'effect isn’t publicly documented, and vanilla values '
            'are wildly inconsistent across tires (BasicTire = 1.0, '
            'Motorcycle = 25,000, HeavyDuty = 600–800). They are '
            'NOT real-world Newtons — the conventional '
            '"set above expected load" rule doesn’t apply.</p>'
            '<p><b>Strongly recommend matching the donor</b> unless '
            'you can A/B test the effect in-game.</p>'
            '<h3>MaxSpeed</h3>'
            '<p>Top speed the tire is rated for, in MT-internal units. '
            'Above this speed grip degrades and you risk instability. '
            'Stock tires are rated comfortably above any vehicle’s '
            'top speed, so this rarely matters.</p>'
            '<h3>RollingResistance</h3>'
            '<p>How much the tire fights against rolling forward. '
            'Lower = better top speed and fuel economy, less natural '
            'engine braking. Stock cars 0.012–0.018.</p>'
            '<h3>WearRate</h3>'
            '<p>How fast the tire wears down. Higher = wears out '
            'sooner. Stock cars ~0.005–0.015. Set to 0 for tires '
            'that never wear.</p>'
            '<h3>WearRate2</h3>'
            '<p>Secondary wear rate for some layouts (kicks in under '
            'heavy load — drift, hard cornering, burnouts). Note: '
            'no vanilla tire actually uses the layout that exposes '
            'this, so it’s rarely available.</p>'
        ),
    },
    {
        'id': 'tire-fields-thermal',
        'title': 'Tire field reference: Thermal & Tread',
        'body': (
            '<h3>ThermalSensitivity</h3>'
            '<p>How much grip changes with temperature. Higher = grip '
            'swings dramatically around the optimal window '
            '(race-tire). Lower = grip stays consistent across '
            'temperatures (street-tire). Set to 0 for "any weather" '
            'tires.</p>'
            '<h3>TireTemperature</h3>'
            '<p>Starting temperature when a vehicle spawns. Mostly '
            'sets the initial state; runtime temperature changes '
            'based on how you drive.</p>'
            '<h3>TreadDepth</h3>'
            '<p>How deep the tire’s tread is. Deeper = better '
            'grip on loose surfaces, worse on dry tarmac. Off-road '
            'tires 0.008+. Race slicks ~0.001.</p>'
        ),
    },
    {
        'id': 'tire-charts-temperature',
        'title': 'Chart: Grip vs Temperature',
        'body': (
            '<p>Dual-line chart showing how the tire’s grip '
            'changes across the temperature range:</p>'
            '<ul>'
            '<li><span style="color:#73c686"><b>Street grip</b></span> (green)</li>'
            '<li><span style="color:#d9a13a"><b>Offroad grip</b></span> (gold)</li>'
            '</ul>'
            '<p><b>Model:</b> Gaussian curve centred on the tire’s '
            'configured TireTemperature, with width inversely '
            'proportional to ThermalSensitivity:</p>'
            '<pre>grip(T) = peak_grip × exp(-((T - peak_temp) / width)²)\n'
            'width   = 70 / (1 + ThermalSensitivity)</pre>'
            '<p>Higher ThermalSensitivity narrows the peak (race '
            'behaviour); low sensitivity flattens it (street '
            'behaviour).</p>'
            + _DISCLAIMER_HEURISTIC
        ),
    },
    {
        'id': 'tire-charts-load',
        'title': 'Chart: Grip Factor vs Load',
        'body': (
            '<p>Single-line chart with 12 sample dots showing how the '
            'tire’s grip falls off as load increases.</p>'
            '<p><b>Model:</b> piecewise:</p>'
            '<pre>load ≤ low                        → factor = 1.0\n'
            'low &lt; load ≤ high                → linear decline 1.0 → 0.7\n'
            'load &gt; high                       → steep decline past 0.7</pre>'
            '<p>Where <code>low</code> is the smaller of (LoadRating, '
            'MaxLoad) and <code>high</code> is the larger. We swap '
            'rather than assume LoadRating &lt; MaxLoad because '
            'vanilla data sometimes inverts the relationship.</p>'
            + _DISCLAIMER_HEURISTIC
        ),
    },
    {
        'id': 'tire-charts-slip',
        'title': 'Chart: Lateral Force vs Slip Angle',
        'body': (
            '<p>Classic tire-engineering shape: cornering force rises '
            'with slip angle, peaks at the optimal slip, then falls '
            'off. The post-peak region is where a real car loses '
            'grip if the driver oversteers.</p>'
            '<p><b>Model:</b> simplified Pacejka rational form:</p>'
            '<pre>F_y(α) = D × (α/α_peak) / (1 + (α/α_peak)²)</pre>'
            '<p>where <code>α_peak ≈ 0.10 rad (5.7°)</code> '
            'for typical tires. Higher CorneringStiffness shifts '
            'the peak earlier and makes it sharper.</p>'
            '<p>The <i>shape</i> is well-defined math; absolute force '
            'magnitude is "kN-relative" because LateralStiffness '
            'units are MT-internal.</p>'
        ),
    },
    {
        'id': 'tire-charts-wear',
        'title': 'Chart: Tread Remaining vs Distance',
        'body': (
            '<p>Linear wear projection. The chart is RELATIVE — a '
            'baseline tire with WearRate = 0.01 wears down 100% over '
            '5,000 km. Tires with WearRate = 0.005 last twice as long; '
            '0.02 lasts half.</p>'
            '<pre>tread%(km) = max(0, 100 − 100 × (WearRate / 0.01) × (km / 5000))</pre>'
            '<p>Absolute mileage isn’t accurate (WearRate units '
            'are unclear), but the comparison across edits is '
            'meaningful.</p>'
        ),
    },
    {
        'id': 'tire-charts-stiffness',
        'title': 'Chart: Stiffness Profile',
        'body': (
            '<p>Five horizontal bars showing each stiffness field '
            'normalised to a 0–1 scale (1.0 = race-tire stiff). '
            'Lets you see the tire’s "shape" at a glance:</p>'
            '<ul>'
            '<li>Race tires — uniformly tall bars across all five</li>'
            '<li>Comfort tires — short to medium bars</li>'
            '<li>Drift tires — tall Lateral / LongSlip but '
            'dropped Cornering</li>'
            '<li>Hauling tires — tall Lateral / Long for load '
            'capacity</li>'
            '</ul>'
            '<p>Reference maxes used for normalisation: Lateral 1.5M, '
            'Long 1.2M, Cornering 1.5, Camber 1.0, LongSlip 400k.</p>'
        ),
    },
    {
        'id': 'tire-archetype',
        'title': 'Use-case classifier (Recommended use)',
        'body': (
            '<p>The classifier scores five archetypes by how well the '
            'tire’s field values match expected patterns:</p>'
            '<ul>'
            '<li><b>Racing / Performance</b> — high Cornering, '
            'high Lateral, high Long, high Camber, low GripMultiplier, '
            'shallow tread</li>'
            '<li><b>Comfort / Daily</b> — low ThermalSensitivity, '
            'moderate Cornering / Lateral, low WearRate</li>'
            '<li><b>Drifting</b> — low Cornering (slide-friendly), '
            'high LongSlipStiffness, softer Lateral, high WearRate</li>'
            '<li><b>Hauling / Heavy-Duty</b> — high LoadRating, '
            'high MaxLoad, lower Cornering, reinforced sidewall</li>'
            '<li><b>Off-road</b> — high positive GripMultiplier, '
            'deep TreadDepth, softer Cornering</li>'
            '</ul>'
            '<p>Each archetype has weighted indicators. The highest '
            'scorer becomes the primary recommendation; if a runner-up '
            'is within 12 points of the winner, it’s shown as a '
            'secondary recommendation. Confidence is the margin '
            'normalised to 0–1.</p>'
            + _DISCLAIMER_HEURISTIC
        ),
    },
]


_CREATOR = {
    'title': 'Engine / Tire Creator',
    'subtitle': 'Fork a vanilla part into a new modded one with custom values.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The Creator is where you build new modded engines '
                'and tires from vanilla templates. Pick a donor, set '
                'the values you want, hit Save — the editor '
                'writes the .uasset/.uexp files plus the matching '
                'DataTable rows.</p>'
                '<p>The fields you can edit depend on which donor '
                'you pick. The editor only shows fields that are '
                'actually serialized in the donor’s binary '
                'layout; missing fields are hidden entirely.</p>'
            ),
        },
        # Engine sections
        *_CREATOR_ENGINE_SECTIONS,
        # Tire sections
        *_CREATOR_TIRE_SECTIONS,
        {
            'id': 'validation',
            'title': 'Input validation: typical vs hard limits',
            'body': (
                '<p>Every numeric field has two ranges:</p>'
                '<ul>'
                '<li><b>Typical range</b> — sane values used by '
                'real-world engines/tires. Going outside this range '
                'is allowed but the field gets a yellow border + '
                'warning hint.</li>'
                '<li><b>Hard limit</b> — absolute floor and '
                'ceiling. Going outside this range is blocked at '
                'save time — these values cause crashes, '
                'freezes, or game refusal-to-load.</li>'
                '</ul>'
                '<p>Hover over any field to see both ranges in a '
                'tooltip. The inline grey text under each field shows '
                'the typical range as a quick reference.</p>'
                '<p>Save is blocked entirely when any field is in '
                'the hard error range. When fields are in the warn '
                'range only, you get a confirmation dialog with the '
                'option to proceed anyway.</p>'
            ),
        },
        {
            'id': 'fork-edit',
            'title': 'Forking and re-editing existing parts',
            'body': (
                '<p>Click a part you’ve already created in the '
                'Generated Parts sidebar, then "Fork" to load it back '
                'into the Creator with all its values. Saving creates '
                'a new part if you change the name; otherwise it '
                'updates the existing one in place.</p>'
                '<p>Fields the original creator inputs are restored '
                'from the part’s <code>.creation.json</code> '
                'sidecar:</p>'
                '<ul>'
                '<li>vehicle_type / vehicle_classes (tires)</li>'
                '<li>fuel_type, peak_torque_rpm, max_hp, peak_hp_rpm '
                '(engines)</li>'
                '<li>level_requirements (engines)</li>'
                '<li>volume_offset (engines)</li>'
                '</ul>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Economy Editor — stack index 3
# ──────────────────────────────────────────────────────────────────────
_ECONOMY = {
    'title': 'Economy Editor',
    'subtitle': 'Adjust cargo payments and economic balance.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The Economy Editor exposes Motor Town’s '
                'cargo payment system. You can rebalance how much '
                'individual cargo types pay per delivery and how '
                'the per-vehicle capacity penalty scales.</p>'
                '<p>Changes are written to MT’s '
                '<code>Balance.json</code> via direct config '
                'overrides — no UE4SS Lua mod required.</p>'
            ),
        },
        {
            'id': 'payment-multipliers',
            'title': 'Payment multipliers',
            'body': (
                '<p>Each cargo type has a payment multiplier scalar '
                'that’s applied to its base payment. The '
                'editable spread is in <code>Balance.json</code>’s '
                'PaymentMultipliers section.</p>'
                '<p>The Cargos_01 DataTable is NOT the place to '
                'adjust cargo payments — that DT carries '
                'metadata only, and Balance.json is what the game '
                'consults at payment-calc time.</p>'
            ),
        },
        {
            'id': 'cargo-scaling',
            'title': 'Per-vehicle capacity penalty',
            'body': (
                '<p>Vanilla MT applies a sqrt-based payment penalty '
                'when a vehicle’s capacity exceeds the cargo’s '
                'natural fit size. Big trucks earn less per unit '
                'than small trucks for the same cargo.</p>'
                '<p>The penalty is reshaped via the Cryovac Cargo '
                'Scaling Lua mod (separate panel — LUA Scripts). '
                'The Economy Editor here can preview how the penalty '
                'curve looks under the Vanilla / Low / High / Off '
                'modes that mod offers.</p>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Bus Route Configurator — stack index 4
# ──────────────────────────────────────────────────────────────────────
_BUS_ROUTE = {
    'title': 'Bus Route Configurator',
    'subtitle': 'Design custom bus routes between stops.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The Bus Route Configurator lets you define new '
                'bus routes by chaining stops, configuring fare '
                'rates, and setting passenger limits per stop.</p>'
            ),
        },
        {
            'id': 'workflow',
            'title': 'Building a route',
            'body': (
                '<p>1. Set the route name + description<br>'
                '2. Add stops in order using the stop picker<br>'
                '3. Configure fare and passenger volume per stop<br>'
                '4. Save — the editor writes the route to '
                'BusRoutes DataTable + matching .uasset assets</p>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Transmission Editor — stack index 5
# ──────────────────────────────────────────────────────────────────────
_TRANSMISSION = {
    'title': 'Transmission Editor',
    'subtitle': 'Create custom transmissions with tuned gear ratios.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The Transmission Editor builds custom '
                '<code>MTTransmissionDataAsset</code> files. You '
                'configure the number of gears, their individual '
                'ratios, the final drive, and the clutch type.</p>'
            ),
        },
        {
            'id': 'gear-ratios',
            'title': 'Choosing gear ratios',
            'body': (
                '<p>Lower gears (1st, 2nd) have higher numerical ratios '
                'for torque multiplication off the line. Higher gears '
                '(top gear, overdrive) have ratios &lt; 1.0 for top-'
                'speed cruising.</p>'
                '<p>Typical car ratios:</p>'
                '<ul>'
                '<li>1st: 3.5–4.5</li>'
                '<li>2nd: 2.0–2.5</li>'
                '<li>3rd: 1.4–1.6</li>'
                '<li>4th: 1.0</li>'
                '<li>5th / 6th: 0.7–0.85 (overdrive)</li>'
                '<li>Final drive: 3.0–4.5</li>'
                '</ul>'
                '<p>Effective ratio at the wheels = gear_ratio × '
                'final_drive. Higher effective ratio = more torque, '
                'lower top speed for that gear.</p>'
            ),
        },
        {
            'id': 'clutch-type',
            'title': 'Clutch type',
            'body': (
                '<p>The clutch enum controls how MT handles automatic '
                'shifting and stall behaviour. Match the clutch type '
                'to the vehicle’s expected drivetrain (manual '
                'cars, automatic trucks, motorcycles all have '
                'different defaults).</p>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Policy Editor — stack index 6
# ──────────────────────────────────────────────────────────────────────
_POLICY = {
    'title': 'Policy Editor',
    'subtitle': 'Tune game-wide gameplay policies.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>Policies are the global rules MT applies to every '
                'session: insurance costs, fine multipliers, vehicle '
                'damage rules, day/night cycle, etc. The Policy Editor '
                'reads MT’s policy DataTable and lets you '
                'override individual fields without touching the rest.</p>'
            ),
        },
        {
            'id': 'safe-edits',
            'title': 'Recommended starting edits',
            'body': (
                '<p>Common quality-of-life policy tweaks:</p>'
                '<ul>'
                '<li><b>Disable insurance</b> — set insurance '
                'cost to 0</li>'
                '<li><b>Reduce fine severity</b> — lower the '
                'speeding/parking fine multipliers</li>'
                '<li><b>Slower vehicle damage</b> — the '
                'CryovacSlowDecay Lua mod is an alternative if you '
                'don’t want to touch the policy DT</li>'
                '<li><b>Skip night</b> — the CryovacSkipNight '
                'Lua mod is the recommended way (no policy edit '
                'needed)</li>'
                '</ul>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# LUA Scripts panel — stack index 7
# ──────────────────────────────────────────────────────────────────────
_LUA_SCRIPTS = {
    'title': 'LUA Scripts',
    'subtitle': 'Generate and deploy UE4SS-based runtime mods.',
    'sections': [
        {
            'id': 'overview',
            'title': 'Overview',
            'body': (
                '<p>The LUA Scripts panel generates UE4SS-based Lua '
                'mods that modify Motor Town’s behaviour at '
                'runtime (rather than via .pak asset overrides). '
                'Each mod has its own card with a description, a few '
                'sliders or toggles, and a Deploy button.</p>'
                '<p>Click Deploy to write the mod folder to '
                '<code>data/lua_mod_output/</code>. From there, copy '
                'the mod folder into MT’s '
                '<code>ue4ss/Mods/</code> directory.</p>'
            ),
        },
        {
            'id': 'ue4ss',
            'title': 'Prerequisite: UE4SS',
            'body': (
                '<p>Every Lua mod here requires UE4SS '
                '(Unreal Engine Scripting System) installed in '
                'Motor Town’s <code>Binaries/Win64/</code> '
                'folder. Without UE4SS, the mods don’t load and '
                'have zero effect.</p>'
                '<p>Each generated mod folder ships a README.txt '
                'with step-by-step UE4SS install instructions. The '
                'short version:</p>'
                '<ol>'
                '<li>Download the latest RE-UE4SS release from GitHub</li>'
                '<li>Extract the zip into MT’s '
                '<code>Binaries/Win64/</code> folder</li>'
                '<li>Copy your mod folders to '
                '<code>Binaries/Win64/ue4ss/Mods/</code></li>'
                '<li>Add a line for each mod to '
                '<code>ue4ss/Mods/mods.txt</code>: '
                '<code>YourModName : 1</code></li>'
                '</ol>'
            ),
        },
        {
            'id': 'mods-cargo-scaling',
            'title': 'Mod: Vehicle Capacity Penalty (cargo scaling)',
            'body': (
                '<p>Reshapes the per-vehicle cargo-payment penalty. '
                'Vanilla MT uses a sqrt-based formula that makes big '
                'trucks earn less per unit than small trucks for the '
                'same cargo.</p>'
                '<p>Modes:</p>'
                '<ul>'
                '<li><b>Vanilla</b> (1.0×) — no change</li>'
                '<li><b>Low</b> (0.5×) — gentler penalty, '
                'big trucks earn more per unit</li>'
                '<li><b>High</b> (1.5×) — steeper penalty, '
                'big trucks earn less</li>'
                '<li><b>Off</b> (0.0×) — no penalty, every '
                'vehicle earns the small-truck rate</li>'
                '</ul>'
                '<p>Targets the PaymentSqrtRatio field on every cargo '
                'row in both Cargos and Cargos_01 DataTables.</p>'
            ),
        },
        {
            'id': 'mods-engine-volume',
            'title': 'Mod: Frog Mod Engine Volume',
            'body': (
                '<p>Auto-generated by the Engine Creator whenever you '
                'set a non-zero Volume Adjustment slider on a modded '
                'engine. Polls every 3 seconds for live MHEngineDataAsset '
                'instances and writes the per-engine MasterVolume '
                'multiplier on each match.</p>'
                '<p>You don’t configure this mod here — it’s '
                'driven entirely by the Engine Creator slider. Listed '
                'in the panel for visibility / disable purposes.</p>'
            ),
        },
        {
            'id': 'mods-production',
            'title': 'Mod: Production + Storage Boost',
            'body': (
                '<p>Two sliders (0.25–10× in 0.25 steps):</p>'
                '<ul>'
                '<li><b>Production Speed</b> — multiplies '
                'ProductionSpeedMultiplier on every recipe in '
                'AMTDeliveryPoint.ProductionConfigs[]. 2× halves '
                'production time.</li>'
                '<li><b>Warehouse Storage</b> — multiplies '
                'MaxStorage on the delivery point AND each '
                'StorageConfigs[].MaxStorage entry.</li>'
                '</ul>'
                '<p>Polls every 5 seconds. Per-instance baselines so '
                'repeated polls don’t compound.</p>'
            ),
        },
        {
            'id': 'mods-contract',
            'title': 'Mod: Contract Payment Boost',
            'body': (
                '<p>Single slider (0.25–5× in 0.25 steps) '
                'that multiplies CompletionPayment on every active '
                'contract. Polls every 5 seconds.</p>'
                '<p>Sets BOTH BaseValue and ShadowedValue on the '
                'FMTShadowedInt64 — the game cross-checks them '
                'for anti-tamper, so writing only one triggers a '
                'reset on the next sync.</p>'
                '<p>Stacks with the Company Profit Boost mod (which '
                'targets per-delivery owner-share via '
                'ServerGiveOwnerProfitShare) — running both '
                'compounds the multipliers.</p>'
            ),
        },
        {
            'id': 'mods-free-depot',
            'title': 'Mod: Free Depot Construction',
            'body': (
                '<p>Binary toggle, no settings. Zeroes the material '
                'cost to build any depot or garage — placing '
                'a Depot_01 / Depot_02 / LargeGarage_01 construction '
                'site completes immediately with no delivered '
                'materials needed.</p>'
                '<p>Targets the /Game/DataAsset/Buildings/Buildings '
                'DataTable. Walks every row whose name contains '
                '"depot" or "garage" and zeros every value in each '
                'step’s Materials TMap.</p>'
            ),
        },
        {
            'id': 'mods-other-cryovac',
            'title': 'Other Cryovac mods at a glance',
            'body': (
                '<ul>'
                '<li><b>Cargo Volume Boost</b> — scales '
                'DumpVolume on Tanker / Dump / DryBulk / Garbage '
                'cargo space components</li>'
                '<li><b>Company Profit Boost</b> — hooks '
                'ServerGiveOwnerProfitShare to multiply per-delivery '
                'owner share on YOUR-company vehicles only</li>'
                '<li><b>Company Vehicle Care</b> — modifies '
                'company vehicle damage / repair behaviour</li>'
                '<li><b>Company Vehicle Limits</b> — changes '
                'AddedVehicleSlots so you can park more cars in '
                'your company</li>'
                '<li><b>EXP Multiplier</b> — boosts character '
                'XP from delivery / driving</li>'
                '<li><b>Population Boost</b> — increases town '
                'population for more cargo demand</li>'
                '<li><b>Skip Night</b> — fast-forwards through '
                'the night portion of the day/night cycle</li>'
                '<li><b>Slow Decay</b> — reduces vehicle '
                'cleanliness / wear decay rates</li>'
                '</ul>'
            ),
        },
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Public registry
# ──────────────────────────────────────────────────────────────────────
HELP_TOPICS: Dict[str, Dict[str, Any]] = {
    'workspace':    _WORKSPACE,
    'creator':      _CREATOR,
    'economy':      _ECONOMY,
    'bus_route':    _BUS_ROUTE,
    'transmission': _TRANSMISSION,
    'policy':       _POLICY,
    'lua_scripts':  _LUA_SCRIPTS,
}


def get_topic(key: str) -> Dict[str, Any]:
    """Return the help-topic dict for *key*, or an empty stub."""
    return HELP_TOPICS.get(key) or {
        'title': 'Help',
        'subtitle': '',
        'sections': [{
            'id': 'na', 'title': 'No help yet',
            'body': '<p>Help content for this page hasn’t been '
                    'written yet.</p>',
        }],
    }
