//########### LTV_ERRORS.json DATA SHAPE ###########//

interface ErrorProceduresData {
  code: string;
  description: string;
  needs_resolved: boolean;
  procedures: string[];
}

export interface LtvErrorsData {
  error_procedures: ErrorProceduresData[];
}