window.FieldCheckExports = {
  generateReportData(state) {
    const discrepancies = state.filteredDiscrepancies;
    const byRoom = {};
    const byFloor = {};
    const byType = {};

    discrepancies.forEach((d) => {
      if (!byRoom[d.room]) byRoom[d.room] = [];
      byRoom[d.room].push(d);
      if (!byFloor[d.roomFloor]) byFloor[d.roomFloor] = 0;
      byFloor[d.roomFloor] += 1;
      if (!byType[d.status]) byType[d.status] = 0;
      byType[d.status] += 1;
    });

    return {
      project: state.job.project,
      generatedAt: new Date().toISOString(),
      totalDiscrepancies: discrepancies.length,
      discrepancies,
      byRoom,
      byFloor,
      byType,
    };
  },

  exportReport(state) {
    const report = this.generateReportData(state);
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    this.downloadBlob(blob, `FieldCheck_Pro_Discrepancy_Report_${state.job.project.replace(/\s+/g, '_')}.json`);
  },

  exportJSON(state) {
    const data = {
      project: state.job.project,
      generatedAt: new Date().toISOString(),
      discrepancies: state.filteredDiscrepancies,
      summary: {
        total: state.totalDiscrepancies,
        byFloor: {},
        byType: {}
      }
    };

    state.filteredDiscrepancies.forEach((d) => {
      if (!data.summary.byFloor[d.roomFloor]) data.summary.byFloor[d.roomFloor] = 0;
      data.summary.byFloor[d.roomFloor] += 1;

      if (!data.summary.byType[d.status]) data.summary.byType[d.status] = 0;
      data.summary.byType[d.status] += 1;
    });

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    this.downloadBlob(blob, `FieldCheck_Pro_Discrepancies_${state.job.project.replace(/\s+/g, '_')}.json`);
  },

  exportCSV(state) {
    const lines = ['Room,Floor,Item,Bid Qty,Spec Qty,Status,Description'];

    state.filteredDiscrepancies.forEach((d) => {
      const status = d.status === 'missingFromBid' ? 'Missing from Bid' : 'Extra in Bid';
      lines.push(
        [
          FieldCheckFormat.sanitizeCsvCell(d.room),
          FieldCheckFormat.sanitizeCsvCell(d.roomFloor),
          FieldCheckFormat.sanitizeCsvCell(d.item),
          d.bidQty,
          d.specQty,
          FieldCheckFormat.sanitizeCsvCell(status),
          FieldCheckFormat.sanitizeCsvCell(d.specDesc || '')
        ].join(',')
      );
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    this.downloadBlob(blob, `FieldCheck_Pro_Discrepancies_${state.job.project.replace(/\s+/g, '_')}.csv`);
  },

  exportPDF() {
    window.print();
  },

  downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }
};
