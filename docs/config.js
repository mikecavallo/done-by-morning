/*
 * Intake form settings for the Done By Morning landing page.
 *
 * With FORM_ENDPOINT left empty, "Send My Brief" opens the visitor's email app with a
 * pre-filled message to CONTACT_EMAIL. That always works, so the page is usable as-is.
 * To collect briefs without relying on the visitor's email app, set FORM_ENDPOINT and
 * FORM_FORMAT to one of the options below.
 *
 * 1. Formspree (or Getform, Basin, FormSubmit and similar form backends)
 *      FORM_ENDPOINT: "https://formspree.io/f/<your-form-id>"
 *      FORM_FORMAT:   "formdata"
 *    Works from GitHub Pages. Submissions arrive by email and in the provider dashboard.
 *
 * 2. Business Runs Better contact.php (self-hosted PHP handler with lead tracking)
 *      FORM_ENDPOINT: "https://businessrunsbetter.com/contact.php"
 *      FORM_FORMAT:   "brb-contact"
 *    Sends the fields contact.php expects (name, email, company, interest, budget,
 *    message, website honeypot, started timestamp) with Accept: application/json.
 *    This page is served from a different origin, so contact.php must send an
 *    Access-Control-Allow-Origin header for this site's origin before the browser will
 *    show the result (no preflight is needed: it is a plain multipart POST). If the
 *    request fails for any reason the page falls back to the mailto link.
 *
 * 3. Netlify Forms (only if this docs/ folder is deployed on Netlify instead of Pages)
 *      FORM_ENDPOINT: "/"
 *      FORM_FORMAT:   "netlify"
 *    The form already carries name="intake" and data-netlify="true".
 *
 * 4. Tally, Typeform or another hosted form
 *      INTAKE_URL: "https://tally.so/r/<form-id>"
 *    The visitor is sent to the hosted form, with name, email, plan and question passed
 *    as URL parameters (map them to hidden fields in the form builder to prefill).
 *    INTAKE_URL takes precedence over FORM_ENDPOINT.
 */
window.DBM_CONFIG = {
  FORM_ENDPOINT: "",
  FORM_FORMAT: "formdata", // "formdata" | "json" | "brb-contact" | "netlify"
  INTAKE_URL: "",
  CONTACT_EMAIL: "hello@businessrunsbetter.com",
};
