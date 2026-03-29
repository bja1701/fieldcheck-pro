window.FieldCheckFormat = {
  floorLabel(floor) {
    if (!floor || floor === 'all') return 'All Floors';
    return floor.charAt(0).toUpperCase() + floor.slice(1);
  },

  getItemStatus(item) {
    if (item.bidQty === item.specQty) return 'ok';
    if (item.bidQty > item.specQty) return 'warning';
    return 'issue';
  },

  getIssueLabel(item) {
    if (item.bidQty > item.specQty) {
      return `Bid has ${item.bidQty - item.specQty} extra`;
    }
    if (item.specQty > item.bidQty) {
      return `${item.specQty - item.bidQty} missing from bid - ADD TO BID`;
    }
    return 'Matched';
  },

  categorizeFixture(name) {
    const value = String(name || '').toLowerCase();
    if (value.includes('toilet')) return 'Toilets';
    if (value.includes('sink') && value.includes('kitchen')) return 'Kitchen Sinks';
    if (value.includes('lav') || value.includes('laboratory')) return 'Lavs';
    if (value.includes('shower') && !value.includes('2nd') && !value.includes('second') && !value.includes('slide')) return 'Showers';
    if (value.includes('2nd') || value.includes('second') || value.includes('slide') || value.includes('hand shower')) return 'Shower 2nd Heads / Slide Bars';
    if (value.includes('tub')) return 'Tubs';
    return 'Other';
  },

  toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  },

  sanitizeCsvCell(value) {
    const str = String(value ?? '');
    const escaped = str.replace(/"/g, '""');
    const prefixed = /^[=+\-@]/.test(escaped) ? `'${escaped}` : escaped;
    return `"${prefixed}"`;
  },

  normalizeJobData(rawData) {
    const errors = [];
    const warnings = [];

    if (!rawData || typeof rawData !== 'object') {
      errors.push('`JOB_DATA` is missing or not an object. Rendering empty dataset.');
      return {
        job: { project: 'Error Loading Data', rooms: [], planNavigation: {} },
        errors,
        warnings
      };
    }

    const roomsInput = Array.isArray(rawData.rooms) ? rawData.rooms : [];
    if (!Array.isArray(rawData.rooms)) {
      errors.push('`JOB_DATA.rooms` is missing or not an array.');
    }

    const rooms = roomsInput.map((room, roomIndex) => {
      const safeRoom = room && typeof room === 'object' ? room : {};
      if (!room || typeof room !== 'object') {
        warnings.push(`Room at index ${roomIndex} is invalid; using defaults.`);
      }

      const itemsInput = Array.isArray(safeRoom.items) ? safeRoom.items : [];
      if (!Array.isArray(safeRoom.items)) {
        warnings.push(`Room "${safeRoom.name || roomIndex}" has non-array items; defaulting to empty list.`);
      }

      return {
        ...safeRoom,
        name: safeRoom.name || `Room ${roomIndex + 1}`,
        floor: safeRoom.floor || 'main',
        cabinetPages: Array.isArray(safeRoom.cabinetPages) ? safeRoom.cabinetPages : [],
        cabinetImages: Array.isArray(safeRoom.cabinetImages) ? safeRoom.cabinetImages : [],
        items: itemsInput.map((item, itemIndex) => {
          const safeItem = item && typeof item === 'object' ? item : {};
          if (!item || typeof item !== 'object') {
            warnings.push(`Invalid item in room "${safeRoom.name || roomIndex}" at index ${itemIndex}; using defaults.`);
          }
          return {
            ...safeItem,
            name: safeItem.name || `Unknown Item ${itemIndex + 1}`,
            bidQty: this.toNumber(safeItem.bidQty),
            specQty: this.toNumber(safeItem.specQty),
            specImage: safeItem.specImage || null,
            specDesc: safeItem.specDesc || ''
          };
        })
      };
    });

    const job = {
      ...rawData,
      project: rawData.project || 'Unknown Project',
      planNavigation: rawData.planNavigation && typeof rawData.planNavigation === 'object' ? rawData.planNavigation : {},
      rooms
    };

    return { job, errors, warnings };
  }
};
