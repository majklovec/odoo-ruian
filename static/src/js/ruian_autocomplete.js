import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { CharField, charField } from "@web/views/fields/char/char_field";

export class RuianAutocomplete extends CharField {
  static template = "web.RuianAutocomplete";
  static events = {
    "input .ruian-input": "handleInput",
    "focus .ruian-input": "handleFocus",
    "click .suggestion-item": "selectSuggestion",
  };
  static props = {
    ...CharField.props,
  };

  setup() {
    super.setup();
    this.orm = useService("orm");
    this.streetId = null;
    this.suggestions = [];
    this.loading = false;
    this.fieldNames = ["street", "city", "zip", "ruian_code"];
    this.debouncedFetch = debounce(this.fetchSuggestions.bind(this), 500);
  }

  handleInput(ev) {
    const query = ev.target.value.trim();
    if (query.length > 2) {
      this.debouncedFetch(query);
    }
  }

  handleFocus() {
    if (this.$input.val().length > 2) {
      this.fetchSuggestions(this.$input.val());
    }
  }

  async fetchSuggestions(query) {
    try {
      this.loading = true;
      this.toggleLoading(true);

      const suggestions = await this._rpc({
        model: "res.partner",
        method: "fetch_ruian_suggestions",
        args: [
          {
            query: query,
            streetId: this.streetId,
            stage: this.streetId ? "number_town" : "street",
          },
        ],
        context: session.user_context,
      });

      this.suggestions = suggestions;
      this.renderSuggestions();
    } finally {
      this.loading = false;
      this.toggleLoading(false);
    }
  }

  selectSuggestion(ev) {
    const $target = $(ev.currentTarget);
    const suggestion = $target.data("suggestion");

    if (suggestion.type === "street") {
      this.streetId = suggestion.payload.id;
      this.updateFields({
        street: suggestion.payload.name,
        city: "",
        zip: "",
        ruian_code: "",
      });
      this.$input.val(`${suggestion.payload.name} `);
    } else {
      this.updateFields({
        street: this.$input.val().split(",")[0],
        city: suggestion.payload.city,
        zip: suggestion.payload.zip,
        ruian_code: suggestion.payload.id,
      });
      this.$input.val(
        `${this.$input.val().split(",")[0]}, ${suggestion.payload.city}, ${
          suggestion.payload.zip
        }`
      );
    }

    this.clearSuggestions();
  }

  updateFields(values) {
    for (const field of this.fieldNames) {
      if (values[field] !== undefined) {
        this.$(`[name="${field}"]`).val(values[field]).trigger("change");
      }
    }
  }

  renderSuggestions() {
    const $list = this.$(".suggestion-list").empty();

    for (const suggestion of this.suggestions) {
      $list.append(
        $(`<div class="suggestion-item" data-suggestion='${JSON.stringify(
          suggestion
        )}'>
            ${this.highlightText(suggestion.display, this.$input.val())}
          </div>`)
      );
    }

    this.$(".suggestion-list").toggle(this.suggestions.length > 0);
  }

  highlightText(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${this.escapeRegex(query)})`, "gi");
    return text.replace(regex, "<strong>$1</strong>");
  }

  escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  clearSuggestions() {
    this.suggestions = [];
    this.$(".suggestion-list").empty().hide();
  }

  toggleLoading(show) {
    this.$(".ruian-spinner").toggle(show);
  }
}

export const ruianAutocomplete = {
  component: RuianAutocomplete,
  supportedTypes: ["char"],
  supportedOptions: [],
  relatedFields: () => [{ name: "display_name", type: "char" }],
  extractProps({ attrs }) {
    return {
      ...super.extractProps({ attrs }),
    };
  },
};

registry.category("fields").add("ruian_autocomplete_widget", ruianAutocomplete);
