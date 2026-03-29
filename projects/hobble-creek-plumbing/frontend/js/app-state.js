function app() {
  const normalized = FieldCheckFormat.normalizeJobData(
    typeof JOB_DATA !== 'undefined' ? JOB_DATA : null
  );

  return {
    tabs: APP_CONFIG.tabs,
    floors: APP_CONFIG.floors,
    planFloors: APP_CONFIG.planFloors,
    reportTypes: APP_CONFIG.reportTypes,

    currentTab: 'bid',
    lightboxImage: null,
    groupByFixture: false,
    showErrorsOnly: false,
    selectedFloor: 'all',
    selectedCabinetFloor: 'all',
    reportFilterFloor: 'all',
    reportFilterType: 'all',
    corrections: JSON.parse(localStorage.getItem('fcpro_corrections') || '{}'),
    correctionModal: { open: false, item: null, roomName: null },
    emailStatus: 'idle',  // idle | sending | sent | error

    job: normalized.job,
    dataErrors: normalized.errors,
    dataWarnings: normalized.warnings,
    lastFocusedElement: null,

    init() {
      this.$watch('lightboxImage', (nextValue) => {
        if (nextValue) {
          this.$nextTick(() => {
            if (this.$refs.lightboxDialog) {
              this.$refs.lightboxDialog.focus();
            }
          });
          return;
        }

        if (this.lastFocusedElement && typeof this.lastFocusedElement.focus === 'function') {
          this.lastFocusedElement.focus();
        }
      });
    },

    openCorrectionModal(item, roomName) {
      this.correctionModal = {
        open: true,
        item: item,
        roomName: roomName,
        specQtyOverride: item.specQty,
      };
    },

    closeCorrectionModal() {
      this.correctionModal = { open: false, item: null, roomName: null };
    },

    applyCorrection(specItem) {
      const key = this.correctionModal.roomName + '::' + this.correctionModal.item.name;
      const correction = {
        specImage: specItem.image_url,
        specDesc: specItem.name + (specItem.model ? ' (' + specItem.model + ')' : ''),
        specModel: specItem.model || '',
        specQtyOverride: this.correctionModal.specQtyOverride,
        isNoMatch: false,
      };
      this.corrections = { ...this.corrections, [key]: correction };
      localStorage.setItem('fcpro_corrections', JSON.stringify(this.corrections));
      this._saveToServer(key, correction, specItem);
      this.closeCorrectionModal();
    },

    applyNoMatch() {
      const key = this.correctionModal.roomName + '::' + this.correctionModal.item.name;
      const correction = {
        specImage: null,
        specDesc: 'No match',
        specModel: '',
        specQtyOverride: this.correctionModal.specQtyOverride,
        isNoMatch: true,
      };
      this.corrections = { ...this.corrections, [key]: correction };
      localStorage.setItem('fcpro_corrections', JSON.stringify(this.corrections));
      this._saveToServer(key, correction, null);
      this.closeCorrectionModal();
    },

    _saveToServer(key, correction, specItem) {
      const sepIdx = key.indexOf('::');
      const room = key.slice(0, sepIdx);
      const bid_name = key.slice(sepIdx + 2);
      const payload = {
        bid_name,
        room,
        spec_items: correction.isNoMatch ? [] : [{
          name: correction.specDesc,
          model: correction.specModel,
          image_url: correction.specImage,
          qty: correction.specQtyOverride,
        }],
        specQtyOverride: correction.specQtyOverride,
        confirmed_by: 'gui',
        job: (typeof JOB_DATA !== 'undefined' && JOB_DATA.project) || '',
        timestamp: new Date().toISOString(),
      };
      fetch(APP_CONFIG.apiBase + '/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {}); // silent fail if server not running
    },

    isItemCorrected(itemName, roomName) {
      return !!(this.corrections[roomName + '::' + itemName]);
    },

    specCatalogForRoom(roomName) {
      if (!roomName) return [];
      const catalog = (typeof JOB_DATA !== 'undefined' && JOB_DATA.specCatalog) ? JOB_DATA.specCatalog : {};
      const roomItems = catalog[roomName];
      return (roomItems && roomItems.length > 0) ? roomItems : Object.values(catalog).flat();
    },

    exportCorrections() {
      const entries = Object.entries(this.corrections).map(([key, val]) => {
        const sepIdx = key.indexOf('::');
        const room = key.slice(0, sepIdx);
        const bid_name = key.slice(sepIdx + 2);
        return {
          bid_name,
          room,
          spec_items: val.isNoMatch ? [] : [{ name: val.specDesc, image_url: val.specImage }],
          confirmed_by: 'gui',
          job: this.job.project || '',
          timestamp: new Date().toISOString(),
        };
      });
      const blob = new Blob([JSON.stringify(entries, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'confirmed_matches.json';
      a.click();
      URL.revokeObjectURL(url);
    },

    openLightbox(image, event) {
      if (!image) return;
      this.lastFocusedElement = event?.currentTarget || document.activeElement;
      this.lightboxImage = image;
    },

    closeLightbox() {
      this.lightboxImage = null;
    },

    formatFloorLabel(floor) {
      return FieldCheckFormat.floorLabel(floor);
    },

    shouldShowItem(item) {
      if (item.bidQty === 0) return false;  // hide spec-only items (not in bid)
      if (this.showErrorsOnly) {
        return item.bidQty !== item.specQty;
      }
      return true;
    },

    filterRoomsByFloor(rooms) {
      if (this.selectedFloor === 'all') return rooms;
      return rooms.filter((room) => room.floor === this.selectedFloor);
    },

    get filteredRooms() {
      const floorFiltered = this.filterRoomsByFloor(this.job.rooms);
      return floorFiltered
        .map((room) => {
          const visibleItems = room.items
            .filter((item) => {
              const isBillable = typeof isBillableItem === 'function' ? isBillableItem(item.name) : true;
              return isBillable && this.shouldShowItem(item);
            })
            .map((item) => {
              const correction = this.corrections[room.name + '::' + item.name];
              if (!correction) return item;
              return {
                ...item,
                specImage: correction.specImage,
                specDesc: correction.specDesc,
                specQty: correction.specQtyOverride != null ? correction.specQtyOverride : item.specQty,
                _corrected: true,
              };
            });
          return { ...room, visibleItems };
        })
        .filter((room) => room.visibleItems.length > 0);
    },

    get filteredGroupedItems() {
      const groups = {
        Toilets: [],
        'Kitchen Sinks': [],
        Lavs: [],
        Showers: [],
        'Shower 2nd Heads / Slide Bars': [],
        Tubs: [],
        Other: []
      };

      const floorFiltered = this.filterRoomsByFloor(this.job.rooms);
      floorFiltered.forEach((room) => {
        room.items.forEach((item) => {
          if (typeof isBillableItem === 'function' && !isBillableItem(item.name)) return;
          if (!this.shouldShowItem(item)) return;

          const correction = this.corrections[room.name + '::' + item.name];
          let groupedItem = { ...item, roomName: room.name, floor: room.floor };
          if (correction) {
            groupedItem = {
              ...groupedItem,
              specImage: correction.specImage,
              specDesc: correction.specDesc,
              specQty: correction.specQtyOverride != null ? correction.specQtyOverride : item.specQty,
              _corrected: true,
            };
          }
          const groupName = FieldCheckFormat.categorizeFixture(item.name);
          groups[groupName].push(groupedItem);
        });
      });

      return Object.entries(groups).filter(([, items]) => items.length > 0);
    },

    getGroupBidTotal(items) {
      if (!Array.isArray(items)) return 0;
      return items.reduce((sum, item) => {
        const qty = Number(item.bidQty);
        return sum + (Number.isFinite(qty) ? qty : 0);
      }, 0);
    },

    get filteredCabinetRooms() {
      if (this.selectedCabinetFloor === 'all') return this.job.rooms;
      return this.job.rooms.filter((room) => room.floor === this.selectedCabinetFloor);
    },

    getPlanFirstPage(floor) {
      const nav = this.job.planNavigation && this.job.planNavigation[floor];
      const pages = nav && nav.pages && nav.pages.length ? nav.pages : [];
      return pages.length ? pages[0] : null;
    },

    get totalItems() {
      let total = 0;
      this.job.rooms.forEach((room) => {
        room.items.forEach((item) => {
          if (item.bidQty === 0) return;
          if (typeof isBillableItem === 'function' && isBillableItem(item.name)) {
            total += 1;
          }
        });
      });
      return total;
    },

    get totalDiscrepancies() {
      let count = 0;
      this.job.rooms.forEach((room) => {
        room.items.forEach((item) => {
          if (item.bidQty === 0) return;
          if (typeof isBillableItem === 'function' && !isBillableItem(item.name)) return;
          const correction = this.corrections[room.name + '::' + item.name];
          const specQty = correction?.specQtyOverride != null ? correction.specQtyOverride : item.specQty;
          if (item.bidQty !== specQty) count += 1;
        });
      });
      return count;
    },

    get matchRate() {
      return this.totalItems > 0
        ? Math.round(((this.totalItems - this.totalDiscrepancies) / this.totalItems) * 100) + '%'
        : '—';
    },

    get filteredDiscrepancies() {
      const discrepancies = [];
      this.job.rooms.forEach((room) => {
        if (this.reportFilterFloor !== 'all' && room.floor !== this.reportFilterFloor) {
          return;
        }

        room.items.forEach((item) => {
          if (item.bidQty === 0) return;
          if (item.bidQty === item.specQty) return;

          const status = item.bidQty < item.specQty ? 'missingFromBid' : 'extraInBid';
          if (this.reportFilterType !== 'all' && status !== this.reportFilterType) {
            return;
          }

          discrepancies.push({
            room: room.name,
            roomFloor: room.floor || 'unknown',
            item: item.name,
            bidQty: item.bidQty,
            specQty: item.specQty,
            status,
            specImage: item.specImage,
            specDesc: item.specDesc || ''
          });
        });
      });
      return discrepancies;
    },

    getItemStatus(item) {
      return FieldCheckFormat.getItemStatus(item);
    },

    getIssueLabel(item) {
      return FieldCheckFormat.getIssueLabel(item);
    },

    openPlanPage(page) {
      window.open(`${APP_CONFIG.planPdfPath}#page=${page}`, '_blank');
    },

    exportReport() {
      FieldCheckExports.exportReport(this);
    },

    exportJSON() {
      FieldCheckExports.exportJSON(this);
    },

    exportCSV() {
      FieldCheckExports.exportCSV(this);
    },

    async sendReportToChad() {
      this.emailStatus = 'sending';
      try {
        const report = FieldCheckExports.generateReportData(this);
        const resp = await fetch(APP_CONFIG.sendReportUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(report),
        });
        this.emailStatus = resp.ok ? 'sent' : 'error';
      } catch {
        this.emailStatus = 'error';
      }
      setTimeout(() => { this.emailStatus = 'idle'; }, 4000);
    },

    exportPDF() {
      FieldCheckExports.exportPDF();
    },

    generateReportData() {
      return FieldCheckExports.generateReportData(this);
    }
  };
}
