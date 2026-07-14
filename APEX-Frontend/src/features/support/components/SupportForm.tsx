import React, { useState } from "react";
import { readPersistedValue, WIZARD_JOB_ID_KEY } from "@/shared/utils/migrationWizardStorage";
import { submitSupportTicket, type SupportTicketCategory } from "../services/supportService";
import { ApiError } from "@/services/http/client";

interface SupportFormProps {
  fixedCategory?: SupportTicketCategory;
  fixedCategoryLabel?: string;
}

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface FormValues {
  name: string;
  email: string;
  subject: string;
  message: string;
  category: SupportTicketCategory;
}

const emptyValues = (category: SupportTicketCategory): FormValues => ({
  name: "",
  email: "",
  subject: "",
  message: "",
  category,
});

const SupportForm: React.FC<SupportFormProps> = ({ fixedCategory, fixedCategoryLabel }) => {
  const [values, setValues] = useState<FormValues>(emptyValues(fixedCategory ?? "general"));
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successTicketId, setSuccessTicketId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const validate = (): boolean => {
    const nextErrors: Partial<Record<keyof FormValues, string>> = {};
    if (!values.name.trim()) nextErrors.name = "Name is required.";
    if (!values.email.trim()) {
      nextErrors.email = "Email is required.";
    } else if (!EMAIL_PATTERN.test(values.email.trim())) {
      nextErrors.email = "Enter a valid email address.";
    }
    if (!values.subject.trim()) nextErrors.subject = "Subject is required.";
    if (!values.message.trim()) nextErrors.message = "Message is required.";
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleChange = (field: keyof FormValues) => (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    setValues((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitError(null);
    setSuccessTicketId(null);

    if (!validate()) return;

    setIsSubmitting(true);
    try {
      const jobId = readPersistedValue(WIZARD_JOB_ID_KEY);
      const response = await submitSupportTicket({
        ...values,
        name: values.name.trim(),
        email: values.email.trim(),
        subject: values.subject.trim(),
        message: values.message.trim(),
        job_id: jobId || null,
      });
      setSuccessTicketId(response.ticket_id);
      setValues(emptyValues(fixedCategory ?? "general"));
      setErrors({});
    } catch (error) {
      setSubmitError(
        error instanceof ApiError
          ? error.message
          : "Could not submit your request. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="support-form" onSubmit={handleSubmit} noValidate>
      <label className="support-field">
        <span>Name</span>
        <input
          type="text"
          value={values.name}
          onChange={handleChange("name")}
          disabled={isSubmitting}
        />
        {errors.name && <span className="support-field-error">{errors.name}</span>}
      </label>

      <label className="support-field">
        <span>Email</span>
        <input
          type="email"
          value={values.email}
          onChange={handleChange("email")}
          disabled={isSubmitting}
        />
        {errors.email && <span className="support-field-error">{errors.email}</span>}
      </label>

      <label className="support-field">
        <span>Subject</span>
        <input
          type="text"
          value={values.subject}
          onChange={handleChange("subject")}
          disabled={isSubmitting}
        />
        {errors.subject && <span className="support-field-error">{errors.subject}</span>}
      </label>

      {fixedCategory ? (
        <div className="support-field">
          <span>Category</span>
          <div className="support-fixed-category">{fixedCategoryLabel ?? fixedCategory}</div>
        </div>
      ) : (
        <label className="support-field">
          <span>Category</span>
          <select value={values.category} onChange={handleChange("category")} disabled={isSubmitting}>
            <option value="general">General question</option>
            <option value="bug">Bug report</option>
            <option value="migration_error">Migration error</option>
          </select>
        </label>
      )}

      <label className="support-field">
        <span>Message</span>
        <textarea
          rows={5}
          value={values.message}
          onChange={handleChange("message")}
          disabled={isSubmitting}
        />
        {errors.message && <span className="support-field-error">{errors.message}</span>}
      </label>

      <button type="submit" className="support-submit-button" disabled={isSubmitting}>
        {isSubmitting ? "Submitting..." : "Submit"}
      </button>

      {successTicketId && (
        <p className="support-success">
          Thanks — your request was received (ticket {successTicketId}). We may follow up by email.
        </p>
      )}
      {submitError && <p className="support-error">{submitError}</p>}
    </form>
  );
};

export default SupportForm;
