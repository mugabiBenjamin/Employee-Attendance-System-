import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";

// Define interface for props
interface ExportButtonsProps {
  onExportCSV: () => Promise<void>;
  onExportPDF: () => Promise<void>;
}

const ExportButtons: React.FC<ExportButtonsProps> = ({
  onExportCSV,
  onExportPDF,
}) => {
  const [isCSVLoading, setIsCSVLoading] = useState<boolean>(false);
  const [isPDFLoading, setIsPDFLoading] = useState<boolean>(false);

  const handleExportCSV = async (): Promise<void> => {
    setIsCSVLoading(true);
    try {
      await onExportCSV();
    } finally {
      setIsCSVLoading(false);
    }
  };

  const handleExportPDF = async (): Promise<void> => {
    setIsPDFLoading(true);
    try {
      await onExportPDF();
    } finally {
      setIsPDFLoading(false);
    }
  };

  return (
    <div className="flex gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={handleExportCSV}
        disabled={isCSVLoading}
        className="flex items-center gap-2"
      >
        <Download className="h-4 w-4" />
        {isCSVLoading ? "Exporting CSV..." : "Export CSV"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={handleExportPDF}
        disabled={isPDFLoading}
        className="flex items-center gap-2"
      >
        <Download className="h-4 w-4" />
        {isPDFLoading ? "Exporting PDF..." : "Export PDF"}
      </Button>
    </div>
  );
};

export default ExportButtons;
