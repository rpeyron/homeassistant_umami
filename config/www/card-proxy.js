
// Helpers

function deepMerge(target, source) {
    const isObject = (val) =>
        val !== null && typeof val === 'object' && !Array.isArray(val);

    const output = Array.isArray(target) ? [...target] : { ...target };

    for (const key in source) {
        if (source[key] === undefined) continue;

        if (isObject(source[key]) && isObject(output[key])) {
            output[key] = deepMerge(output[key], source[key]);
        } else if (Array.isArray(source[key]) && Array.isArray(output[key])) {
            output[key] = output[key].map((item, index) =>
                source[key][index] ? deepMerge(item, source[key][index]) : item
            ).concat(source[key].slice(output[key].length));
        } else {
            output[key] = source[key];
        }
    }

    return output;
}

// Pseudo template liquid filters engine
function renderTemplate(template, data, extraFilters = {}) {
    if (typeof template !== 'string') return template;

    const filters = {
        capitalize: s => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase(),
        upcase: s => s.toUpperCase(),
        replace: (s, pattern, repl) => s.replace(new RegExp(pattern, 'g'), repl || ''),
        truncate: (s, len = 10) => s.length > Number(len) ? s.slice(0, Number(len)) + '...' : s,
        default: (v, d) => v || d,
        no_spaces: s => s.replace(/\s+/g, ''),
        ...extraFilters
    };

    return template.replace(/\{\{(.*?)\}\}/gs, (match, content) => {
        const parts = content.trim().split(/\s*\|\s*/);
        let result = parts[0].trim().split('.').reduce((obj, k) => obj?.[k], data) ?? '';

        for (let i = 1; i < parts.length; i++) {
            const filterPart = parts[i].trim();
            const colonIndex = filterPart.indexOf(':');
            const filterName = colonIndex > 0 ? filterPart.slice(0, colonIndex).trim() : filterPart.trim();
            const filterArgs = colonIndex > 0 ? filterPart.slice(colonIndex + 1).trim() : '';

            const filter = filters[filterName];
            if (!filter) continue;

            const args = filterArgs ? filterArgs.split(',').map(arg => {
                arg = arg.trim();
                return data[arg] ?? (/^["'](.*)["']$/.exec(arg)?.[1] ?? parseFloat(arg) ?? arg);
            }) : [];

            result = filter(String(result), ...args);
        }

        return result;
    });
}


// Card Proxy Base - common code for all cards using Proxy data

class CardProxyBase extends HTMLElement {
    async setConfig(config) {
        this.config = config;

        this.lastUpdate = null
        this.lastError = null
        this.lastResult = null

        this.refreshGraph();

        if (config.refresh_seconds)
            setTimeout(() => this.refreshGraph(), config.refresh_seconds * 1000);
    }

    async updateData() {

        if (!this._hass) return null
        if (!this.config?.query_id) return null

        if (this.lastResult && this.lastUpdate && ((Date.now() - this.lastUpdate) < this.config.refresh_seconds * 1000))
            return this.lastResult

        try {
            const result = await this._hass.callApi('GET', 'proxy_scripts/' + this.config.query_id);
            this.lastError = null
            this.lastResult = result
            this.lastUpdate = Date.now()
        } catch (error) {
            console.error("Error loading  data:", error);
            this.lastError = error
        }

        return this.lastResult
    }

    async refreshGraph() {

    }

    set hass(hass) {
        this._hass = hass;
        if (this._hass && !this.once) { this.once = true; this.refreshGraph(); }
    }

    /*
    getCardSize() {
      return 2;
    }
    */

    static getStubConfig() {
        return {
            refresh_seconds: 3600,
            query_id: "visits",
        };
    }

}


// Card Proxy Chartjs - display Chartjs graph from Proxy data
// https://www.chartjs.org/docs/latest/

class CardProxyChartjs extends CardProxyBase {
    async setConfig(config) {

        if (!this.content) {
            this.innerHTML = `
        <ha-card>
          <div style="position: relative; min-height: ${config.height ?? 160}px" >
            <canvas id="jsonChart" height="${config.height ?? 160}" style="display: none;"></canvas>
            <div id="loadingSpinner" style="
              position: absolute;
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              display: flex;
              flex-direction: column;
              align-items: center;
              gap: 10px;
            ">
              <ha-spinner active size="large"></ha-spinner>
              <div>Loading data...</div>
            </div>
          </div>
        </ha-card>
      `;
            this.content = true;
        }

        // Charger Chart.js si pas déjà là
        if (!window.Chart) {
            const chartJs = document.createElement("script");
            chartJs.src = "https://cdn.jsdelivr.net/npm/chart.js";
            document.head.appendChild(chartJs);
            await new Promise((resolve) => (chartJs.onload = resolve));
        }

        super.setConfig(config)
    }

    displaySpinner(state, message) {
        const spinner = this.querySelector("#loadingSpinner");
        if (spinner) spinner.style.display = (state) ? "flex" : "none";
        if (message) spinner.innerHTML = `
        <div style="color: var(--error-color);">${message}</div>
        `;
    }

    async refreshGraph() {
        // Afficher spinner
        this.displaySpinner(true);
        const canvas = this.querySelector("#jsonChart");
        if (canvas) canvas.style.display = "none";

        try {
            const result = await this.updateData();

            if (this.lastError) {
                this.displaySpinner(true, `${this.lastError.body?.error ?? this.lastError.error ?? "Error loading data"} </i>(${this.lastError.status_code ?? ""})</i>`);
                return;
            }

            let data = result
            if (!data) return
            const title = this.config.title ?? "Chartjs";

            // Création du graphique
            const ctx = canvas.getContext("2d");
            if (this.chart) this.chart.destroy();
            const config = deepMerge({
                type: "line",
                data: data,
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: true },
                        title: { display: true, text: title }
                    },
                    scales: {
                        x: { display: true },
                        y: { display: true },
                    }
                },
            }, this.config?.chartjs);
            // console.log(config, this.config, data);
            this.chart = new Chart(ctx, config);

            // Cacher spinner, afficher graphique
            this.displaySpinner(false);
            canvas.style.display = "block";

        } catch (error) {
            console.error("Error loading Proxy data:", error);

            // Erreur dans spinner
            this.displaySpinner(true, "Error loading data");
        }
    }


    static getStubConfig() {
        return {
            ...super.getStubConfig(),
            title: "Proxy Chartjs",
            height: "160",
        };
    }
}

customElements.define("card-proxy-graph", CardProxyChartjs);

window.customCards = window.customCards || [];
window.customCards.push({
    type: "card-proxy-graph",
    name: "Card Proxy Chartjs",
    description: `Custom card for Proxy Chartjs graph.

  You will need to use Proxy integration and set query_id accordingly

  You can set up the refresh rate with refresh_seconds

  You may also customize the display by providing ChartJS configuration
  override with chartjs config key,

  Config example:
    type: custom:card-proxy-graph
    refresh_seconds: 3600
    query_id: umami
    title: Title of the graph
    height: "160"
    chartjs:
      options:
        plugins:
          legend:
            display: false
`
});


// Card Proxy Table - display table from Proxy data, with configurable columns and grid template

class CardProxyTable extends CardProxyBase {
    async setConfig(config) {

        if (!config.columns?.length) {
            throw new Error("You must define columns")
        }

        super.setConfig(config)
    }

    async refreshGraph() {

        const results = await this.updateData();

        if (this.config.columns && Array.isArray(this.config.columns) && results && Array.isArray(results)) this.innerHTML = `
      <ha-card style="width: 100%; max-width:100%; overflow: hidden;">
        <style>
        card-proxy-table table { display: grid; width: 100%; max-width: 100%;  }
        card-proxy-table tbody, card-proxy-table tr { display: contents; }
        card-proxy-table td,th { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        </style>
        ${(this.config.title) ? "<h1>" + this.config.title + "</h1>" : ""}
        <table style="grid-template-columns: ${this.config.grid_template ?? "repeat(" + this.config.columns.length + ", 1fr)"}">
         <tr>
         ${this.config.columns.map(col =>
            `<th>
           ${col.label ?? col.key}
           </th>`).join("")}
         </tr>
         ${results.slice(0, this.config.max ?? 10).map(l =>
                `<tr>
           ${this.config.columns.map(col => `<td>${renderTemplate(col.template, l) ?? l[col.key]}</td>`).join("")}
          </tr>`).join("")}
      </ha-card>
    `;

    }

    static getStubConfig() {
        return {
            ...super.getStubConfig(),
            columns: [{ "key": "path", "label": "Page", template: "{ title |default: path}" }, { "key": "count", "label": "Views" }],
            grid_template: "1fr 5em",
            max: 10
        };
    }

}

customElements.define("card-proxy-table", CardProxyTable);

window.customCards = window.customCards || [];
window.customCards.push({
    type: "card-proxy-table",
    name: "Card Proxy Table",
    description: `Custom card for Proxy tables.

  You will need to use Proxy integration and set query_id accordingly

  You can set up the refresh rate with refresh_seconds

  You have to define the columns config to list the columns you want in
  which order.

  Config example:
    type: custom:card-proxy-table
    refresh_seconds: 3600
    query_id: umami_pages
    title: Optional Title
    columns:
      - key: path
        label: Page
        template: "<a href='{{path}}' target='_blank'>{{title | replace: ' text', '' | default: 'No title' }}</a>"
      - key: count
        label: Views
    grid_template: "1fr 5em"
    max: 10
  `,
});

