/**
 * Javascript needed for the metadata upload functionality of the JDRF MIBC website.
 */

// Dragging DOM elements
// Credit: https://css-tricks.com/snippets/jquery/draggable-without-jquery-ui/
(function($) {
    $.fn.drags = function(opt) {

        opt = $.extend({handle:"",cursor:"move"}, opt);

        if(opt.handle === "") {
            var $el = this;
        } else {
            var $el = this.find(opt.handle);
        }

        return $el.css('cursor', opt.cursor).on("mousedown", function(e) {
            if(opt.handle === "") {
                var $drag = $(this).addClass('draggable');
            } else {
                var $drag = $(this).addClass('active-handle').parent().addClass('draggable');
            }
            var z_idx = $drag.css('z-index'),
                drg_h = $drag.outerHeight(),
                drg_w = $drag.outerWidth(),
                pos_y = $drag.offset().top + drg_h - e.pageY,
                pos_x = $drag.offset().left + drg_w - e.pageX;
            $drag.css('z-index', 1000).parents().on("mousemove", function(e) {
                $('.draggable').offset({
                    top:e.pageY + pos_y - drg_h,
                    left:e.pageX + pos_x - drg_w
                }).on("mouseup", function() {
                    $(this).removeClass('draggable').css('z-index', z_idx);
                });
            });
            e.preventDefault(); // disable selection
        }).on("mouseup", function() {
            if(opt.handle === "") {
                $(this).removeClass('draggable');
            } else {
                $(this).removeClass('active-handle').parent().removeClass('draggable');
            }
        });

    }
})(jQuery);

/**
 * Takes an array of errors from the sample metadata validation and populates 
 * all the widgets on our upload_metadata page to allow the user to jump to the pages
 * in the DataTable with the error.
 */
function populateErrorsList(table, response) {
    $('#errors-count').html('<b>' + response.errors_list.length + '</b>');
    $('#errors-list ul').empty();

    var error_list_html = "";
    response.errors_list.slice(0,10).forEach(function(err) {
        error_list_html += "<li data-row=\"" + err.row + "\" data-col=\"" + err.col + "\"><span class='error-link'>" 
                            + "<b>Row</b>: " + (err.row+1) + ", <b>Column</b>: " + err.col + " - " + err.mesg + "</span></div></li>";
    });

    $('#errors-list ul').html(error_list_html);
    $('#errors-list li').on('click', function(e) {
        var error_row = $(this).data('row');
        var error_col = $(this).data('col');

        // We break pages up by 12 so we want to figure out what our page number is based off of that
        // TODO: The page num should probably be a var somewhere in case we change it in the DataTables config
        var page_num = Math.floor(error_row / 20)
        table.page(page_num).draw(false);
        //table.row(error_row).scrollTo(false);

        var col_idx = table.column(error_col + ':name').index()
        var cell_node = table.cell(error_row, col_idx).node();

        $('td.selected').removeClass('selected')
        $(cell_node).addClass('selected');
        setTimeout(function() {
            $(cell_node).removeClass('selected');
        }, 5000);


        $('div.dataTables_scrollBody').scrollTop(0).scrollTop($(cell_node).position().top);
        $('div.dataTables_scrollBody').scrollLeft(0).scrollLeft($(cell_node).position().left);
    });
}

/**
 * Updates the sample metadata errors DataTable with new error rows.
 */
function updateErrorsDataTable(table, response) {
    tables_json = JSON.parse(response.errors_datatable);
    table.clear()
    table.rows.add(tables_json, false).draw();
    //$('#metadata_file_preview').dataTable().fnAdjustColumnSizing()
    table.columns.adjust().draw();
}

jQuery(document).ready(function() {
    $.ajaxSetup({beforeSend: function(xhr, settings){
        xhr.setRequestHeader('X-CSRFToken', 
                             $("input[name='csrfmiddlewaretoken']").val());
      }});

    // Hope this doesn't break the datatables error tooltips...
    $('[data-toggle="tooltip"]').tooltip()

    $('#error-list-modal').drags({ handle: ".modal-header" });

    var editor_opts = {
        table: "#metadata_file_preview",
        fields: [
            { label: 'Sample ID', name: 'sample_id' },
            { label: 'Host Subject ID', name: 'host_subject_id' },
            { label: 'Subject Age', name: 'subject_age' },
            { label: 'Subject Sex', name: 'subject_sex' },
            { label: 'Ethnicity', name: 'ethnicity' },
            { label: 'Collection Date', name: 'collection_date'},
            { label: 'Host Body Mass Index', name: 'host_body_mass_index' },
            { label: 'Host Diet', name: 'host_diet' },
            { label: 'Host Disease', name: 'host_disease' },
            { label: 'Host Body Product', name: 'host_body_product' },
            { label: 'Host Family Relationship', name: 'host_family_relationship' },
            { label: 'Host Genotype', name: 'host_genotype' },
            { label: 'Host Phenotype', name: 'host_phenotype' },
            { label: 'Gastrointestinal Disorder', name: 'gastrointest_disord' },
            { label: 'IHMC Medication Code', name: 'ihmc_medication_code' },
            { label: 'Subject Taxonomy ID', name: 'subject_tax_id' },
            { label: 'Sourced Material ID', name: 'source_material_id' },
            { label: 'Isolation Source', name: 'isolation_source' },
            { label: 'Sample Material Process', name: 'sample_mat_process' },
            { label: 'Sample Store Duration', name: 'sample_store_dur' },
            { label: 'Sample Store Temperature', name: 'sample_store_temp' },
            { label: 'Sample Volume Mass', name: 'sample_vol_mass' },
            { label: 'Variable Region', name: 'variable_region' },
            { label: 'Organism Count', name: 'organism_count' },
            { label: 'Sequencer', name: 'sequencer' },
            { label: 'Number of Reads', name: 'read_number' },
            { label: 'Filename', name: 'filename' },
            { label: 'MD5 Checksum', name: 'md5_checksum' }
        ]
    };

    var local_editor = new $.fn.dataTable.Editor(editor_opts);
    var ajax_editor = new $.fn.dataTable.Editor(
        $.extend(true, {
            ajax: "/metadata/sample",
        }, editor_opts)
    );

    var is_other_data_type = false;
    $('#sample_type').on('change', function() {
        var value = $(this).val();
        $("#paired_id").val("");
        $("#paired").val("no");
        $('#paired-id-div').addClass('hidden');

        if (value == "other") {
            $('#analysis_desc_div').removeClass('hidden');
            $('#paired-end-div').addClass('hidden');
            $("#paired").val("false");
            is_other_data_type = true;
        } else {
            $('#analysis_desc').val("");
            $('#analysis_desc_div').addClass('hidden');
            $('#paired-end-div').removeClass('hidden');
            is_other_data_type = false;

            if (value == "16S") {
                $('#paired_id').val("_R1_001");
            } else if (value == "wmgx" || value == "wmtx") {
                $("#paired_id").val(".R1");
            }
        }
    });

    $('#paired').on('change', function() {
        var value = $(this).val();


        if (value === "true") {
            $('#paired-id-div').removeClass('hidden');
            $('#paired_id').prop('required', true);
        } else {
            $('#paired-id-div').addClass('hidden');
            $('#paired_id').prop('required', false);
            $('#paired_id').val("");
        }
    });

    // On page load we want to see if a cookie exists to indicate study metadata has been created for this file.
    if (Cookies.get('study_metadata') == '1') {
        // Need to do an AJAX request here to parse the contents of our CSV file and fill in 
        // form data
        $.ajax({
            url: '/metadata/study',
            method: 'GET',
            success: function(data) {
                var form_elts = data.study_form;
                $.each(form_elts, function(key, val) {
                    $('#panel_study_metadata #' + key).val(val);
                });

                if ($('#sample_type').val() === "other") {
                    $('#analysis_desc_div').removeClass('hidden');
                    $('#paired-end-div').addClass('hidden');
                    is_other_data_type = true;
                } else {
                    $('#paired option:eq(2)').prop('selected', true)
                    $('#paired-end-div').removeClass('hidden');

                    if ($('#paired').val() === "true") {
                       $('#paired-id-div').removeClass('hidden');
                       $('#paired option:eq(1)').prop('selected', true)
                    }
 
                    is_other_data_type = false;
                }
            },
            error: function(data) {
                // Something clearly went wrong here so let's remove our cookie
                 // for the time being...
                 Cookies.remove('study_metadata');
            }
        });

        // Load the metadata file and hide our panel.
        $('#panel_study_metadata .panel-body').hide();
        $('#panel_study_metadata .panel-heading').css('cursor', 'pointer');
        $('#panel_study_metadata .panel-heading').html('<h3 class="panel-title">Study Metadata <span class="pull-right glyphicon glyphicon-ok green"></span></h3>');
        $('#panel_study_metadata .panel-heading').on('click', function() {
            $('#panel_study_metadata .panel-body').slideToggle();
        })

        $('#panel_sample_metadata .panel-heading').css('opacity', 1)
        $('#panel_sample_metadata .panel-body').show();
        $('#panel_sample_metadata .panel-heading').css('cursor', 'pointer');
        $('#panel_sample_metadata .panel-heading').on('click', function() {
            $('#panel_sample_metadata .panel-body').slideToggle();
        })
        
        $('#metadata_complete').removeClass('hidden');
        $('#date_format_audit').removeClass('hidden');
    }

    if (Cookies.get('sample_metadata') == '1') {
        $('#panel_sample_metadata .panel-body').hide();
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-ok green"></span></h3>');
        $('#upload_success').removeClass('hidden');
        $('#date_format_audit').removeClass('hidden');
    }

    $('#study_metadata_form').validator({
        custom: {
            'pair-identifier': function(el) {
                var pair_identifier = $(el).val();
                var pair_ident_re = /[-a-zA-Z0-9_.]+/;
                if ($('#paired').val() == "true" && pair_ident_re.test(pair_identifier) == false) {
                    return "Must provide valid pair-identifier (e.g. R1, 1, etc.)";
                }
            }
        }
    });

    $('#study_metadata_form').validator().on('submit', function(e) {
        if (e.isDefaultPrevented()) {
            // Do nothing for the time being.
        } else {
           e.preventDefault();

            // Write our form data to a CSV file
            $.ajax({
                url: '/metadata/study',
                data: $('#study_metadata_form').serialize(),
                method: 'POST',
                processData: false,
                success: function(data) {
                    $('#validation_error_single').hide();

                    $('#panel_study_metadata .panel-body').slideUp();
                    $('#panel_study_metadata .panel-heading').html('<h3 class="panel-title">Study Metadata <span class="pull-right glyphicon glyphicon-ok green"></span></h3>');
                    $('#panel_study_metadata .panel-heading').on('click', function() {
                        $(this).css('cursor', 'pointer');

                        $('#panel_study_metadata .panel-body').slideToggle();
                    });

                    $('#panel_sample_metadata .panel-heading').css('opacity', '1');
                    $('#panel_sample_metadata .panel-body').slideDown();
                    Cookies.set('study_metadata', "1");
                },
                error: function(data) {
                    // If something goes wrong here we want to let the user know and to likely contact us for help.
                    $('#panel_study_metadata .panel-heading').html('<h3 class="panel-title">Study Metadata <span class="pull-right glyphicon glyphicon-remove red"></span></h3>');
                    $('#validation_error_single').html("<div class='glyphicon glyphicon-ban-circle'></div>" +
                                                       "<div>Error processing study metadata. Please contact JDRF MIBC support.</div>");
                    $('#validation_error_single').show();
                }
            })

        }
    })

    $('#metadata_file_upload').fileinput({
        showPreview: false,
        uploadAsync: false,
        layoutTemplates: {progress: ''},
        uploadUrl: '/metadata/sample',
        msgPlaceholder: 'Select metadata file to upload...',
        uploadExtraData: function() { 
           return {
               'csrfmiddlewaretoken': $("input[name='csrfmiddlewaretoken']").val(),
               'other_data_type': is_other_data_type,
           }
        }
    });

    var row_update = false;
    $('#metadata_file_preview').on('click', 'tbody td:not(:first-child):not(.DTE)', function(e) {
        local_editor.inline( this, { onBlur: 'submit' } );
    });


    var table = $('#metadata_file_preview').DataTable({
       dom: "<'row'<'#edit_buttons.col-md-4 col-md-offset-8'B>>" +
            "<'row'<'col-sm-6'l><'col-sm-6'f>>" +
            "<'row'<'col-sm-12'tr>>" +
            "<'row'<'col-sm-5'i><'#errors_list_button.col-md-2'><'col-sm-5'p>>",
       pageLength: 20,
       searching: false,
       deferLoading: 0,
       lengthChange: false,
       scrollY: 425,
       scrollX: 400,
       scrollCollapse: false,
       order: [],
       columns: [
           {data: 'sample_id', name: 'sample_id'},
           {data: 'host_subject_id', name: 'host_subject_id'},
           {data: 'subject_age', name: 'subject_age'},
           {data: 'subject_sex', name: 'subject_sex'},
           {data: 'ethnicity', name: 'ethnicity'},
           {data: 'collection_date', name: 'collection_date'},
           {data: 'host_body_mass_index', name: 'host_body_mass_index'},
           {data: 'host_diet', name: 'host_diet'},
           {data: 'host_disease', name: 'host_disease'},
           {data: 'host_body_product', name: 'host_body_product'},
           {data: 'host_family_relationship', name: 'host_family_relationship'},
           {data: 'host_genotype', name: 'host_genotype'},
           {data: 'host_phenotype', name: 'host_phenotype'},    
           {data: 'gastrointest_disord', name: 'gastroinstest_disord'},
           {data: 'ihmc_medication_code', name: 'ihmc_medication_code'},
           {data: 'subject_tax_id', name: 'subject_tax_id'},
           {data: 'source_material_id', name: 'source_material_id'},
           {data: 'isolation_source', name: 'isolation_source'},
           {data: 'samp_mat_process', name: 'samp_mat_process'},
           {data: 'samp_store_dur', name: 'samp_store_dur'},
           {data: 'samp_store_temp', name: 'samp_store_temp'},
           {data: 'samp_vol_mass', name: 'samp_vol_mass'},
           {data: 'variable_region', name: 'variable_region'},
           {data: 'organism_count', name: 'organism_count'},
           {data: 'sequencer', name: 'sequencer'},
           {data: 'read_number', name: 'read_number'},
           {data: 'filename', name: 'filename'},
           {data: 'md5_checksum', name: 'md5_checksum'}
       ],
       columnDefs: [
           {
               targets: '_all',
               createdCell: function(td, cellData, rowData, row, col) {
                   var col_name = table.column(col).dataSrc();
                   if (rowData[col_name + "_error"] == true) {
                           $(td).css('color', 'white');
                           $(td).css('font-weight', 'bold');
                           $(td).css('background-color', 'red');
                           $(td).attr('data-toggle', 'tooltip').attr('title', rowData[col_name + "_validation_msg"]);
                           $(td).html(cellData);
                   }
               }
           },
           {
               targets: 5,
               render: function(data) {
                   return moment(data).format('YYYY-MM-DD');
               }
           }
       ],
       buttons: [
           {
               text: 'Submit changes',
               className: 'datatables-submit',
               init: function() {
                    this.disable();
               },
               action: function() {
                    ajax_editor.edit(changed_rows, false).submit();

                    changed_rows.length = 0;
                    table.buttons([0,1]).disable();
                    $("#edit_buttons").hide();
               }
           },
           {
               text: 'Discard changes',
               init: function() {
                   this.disable();
               },
               action: function() {
                    table.clear();
                    table.rows.add(tables_json, false).draw();

                    changed_rows.length = 0;
                    table.buttons([0,1]).disable();
                    $("#edit_buttons").hide();
               }
           }
       ]
    });

    $('div#errors_list_button').html('<button type="button" class="btn btn-default" data-backdrop="false" data-toggle="modal" ' +
                                     'data-target="#error-list-modal"><span class="glyphicon glyphicon-exclamation-sign"' +
                                     'aria-hidden="true"></span> Show Error List</button>');

    $('div#errors_list_button button').on('click', function(e) {
        // This is pretty ugly but is my hack to get around our dialog covering the background and not letting us click...
        var dialog_left_pos = $('#error-list-modal .modal-content').position().left;
        if (dialog_left_pos <= 0) {
            $('#error-list-modal .modal-content').css('left', 250);
        }
    })

    var changed_rows = [];
    var open_vals = "";
    var table_json = "";

    // Because Firefox and Safari handle blur a little different need this here
    // Also handle when someone hits the 'Escape' key when editing.
    $('#metadata_file_preview').on('keydown', 'tbody td:not(:first-child):not(div)', function(e) {
        if (e.which == 13) {
            $(this).blur();
        }
    });

    $('#metadata_file_preview').on('blur', 'tbody td:not(:first-child):not(div)', function(e) {
        if (e.which == 0 && row_update == false) {
            e.stopImmediatePropagation();
        } else {
            if (open_vals !== JSON.stringify( local_editor.get() )) {
                $(this).css('color', 'black');
                $(this).css('background-color', 'yellow');
                row_update = true;

            } else {
                row_update = false;
            }

            $(this).tooltip('hide');

            // Depending on the event triggering blur we're better off manually triggering the submit.
            local_editor.submit();
        }
    });

    local_editor.on('open', function() {
        open_vals = JSON.stringify( local_editor.get() );
    });

    local_editor.on('postEdit', function (e, json, data) {
        if (row_update == true) {
            // Store the row id so it can be submitted with the Ajax editor in future
            changed_rows.push( '#'+data.DT_RowId );

            // Enable the save / discard buttons
            $("#edit_buttons").show();
            table.buttons([0,1]).enable();
        }
    });

    ajax_editor.on('preSubmit', function(e, data, action) {
        $('#panel_sample_metadata').addClass('loading');
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-refresh glyphicon-spin"></span></h3>');
    });

    ajax_editor.on('postSubmit', function (e, resp, data, action, xhr) {
        $('#panel_sample_metadata').removeClass('loading');
        if (resp.error) {
            $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-remove red"></span></h3>');
            Cookies.remove('sample_metadata');

            populateErrorsList(table, resp);
            updateErrorsDataTable(table, resp);
        } else {
            $('#datatables_div').hide();
            $('#error_spreadsheet').addClass('hidden');

            if ($('#error-list-modal').hasClass('in')) {
               $('#error-list-modal').modal('hide');
            }

            $('#panel_sample_metadata .panel-body').slideUp();
            $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-ok green"></span></h3>');
            Cookies.set('sample_metadata', 1);

            $('#upload_success').removeClass('hidden');
            $('#validation').addClass('hidden');
            $('#date_format_audit').removeClass('hidden');
        }
    });

    $('#metadata_file_preview').on('draw.dt', function () {
        $('[data-toggle="tooltip"]').tooltip({
            container : 'body'
        });
    });

    $('#metadata_file_upload').on('filelock', function(event, filestack, extraData) {
        $('#panel_sample_metadata').addClass('loading')
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-refresh glyphicon-spin"></span></h3>');
    });

    $('#metadata_file_upload').on('fileunlock', function(event, filestack, extraData) {
        $('#panel_sample_metadata').removeClass('loading')
    });

    $('#metadata_file_upload').on('filebatchuploaderror', function(event, data, msg) {
        var response = data.response;
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-remove red"></span></h3>');
        Cookies.remove('sample_metadata');

        if (response.hasOwnProperty('error_msg')) {
            // We have a larger structural problem here so don't render 
            // the table and just display the error message.
            $('#datatables_div').hide();
            $('#error_spreadsheet').addClass('hidden')
            
            // If we have a mismatch in the columns supplied in our metadata vs what is expected
            // in the schema we can list out all the 
            var error_single_html = "";
            if ("mismatch_cols" in response) {
                // We should get back two lists of columns here. One contains extra columns 
                // while the other will contain any missing columns.
                extra_cols = response['mismatch_cols'][0]
                missing_cols = response['mismatch_cols'][1]

                error_single_html += "<div class='glyphicon glyphicon-ban-circle'></div>" +
                                     "<div>" + response['error_msg'] + ":" + "</div><br />" +
                                     "<div id='mismatch_cols'>";

                if (missing_cols.length > 0) {
                    error_single_html += "<b>Missing Columns:</b><br /><ul>";

                    for (var col in missing_cols) {
                        error_single_html += "<li><b>" + missing_cols[col] + "</b></li>";
                    }

                    error_single_html += "</ul><br />";
                }

                if (extra_cols.length > 0) {
                    error_single_html += "<b>Extra Columns:</b><br /><ul>";

                    for (var col in extra_cols) {
                        error_single_html += "<li><b>" + extra_cols[col] + "</b></li>";
                    }
                }

                error_single_html += "</ul></div>";

                $('#validation_error_single').html(error_single_html);
            } else {
                $('#validation_error_single').html("<div class='glyphicon glyphicon-ban-circle'></div>" +
                                                   "<div>" + response['error_msg'] + "</div>");
            }

            $('#validation_error_single').removeClass('hidden');
            $('#validation').removeClass('hidden');
        } else {
            $('#upload_success').addClass('hidden');
            $('#date_format_audit').addClass('hidden')
            Cookies.remove('sample_metadata');

            populateErrorsList(table, response);

            $('#validation_error_single').addClass('hidden');
            $('#error_spreadsheet').removeClass('hidden')
            $('#datatables_div').show();

            $('#validation').css('width', '100%');
            $('#validation').removeClass('hidden');
            $("#edit_buttons").hide();

            updateErrorsDataTable(table, response);
        }
     });

     $('#metadata_file_upload').on('change', function(event) {
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata</h3>');
        $('#validation').addClass('hidden');
        $('#upload_success').addClass('hidden');
        $('#date_format_audit').addClass('hidden');

        if ($('#error-list-modal').hasClass('in')) {
            $('#error-list-modal').modal('hide');
        }
     });
     
     $('#metadata_file_upload').on('filebatchuploadsuccess', function(event, files, extra) {
        $('#panel_sample_metadata .panel-body').slideUp();
        $('#panel_sample_metadata').removeClass('loading');
        $('#panel_sample_metadata .panel-heading').html('<h3 class="panel-title">Sample Metadata <span class="pull-right glyphicon glyphicon-ok green"></span></h3>');
        Cookies.set('sample_metadata', 1);

        $('#upload_success').removeClass('hidden');
        $('#date_format_audit').removeClass('hidden');
     });

     // The javascript below handles autocompleting any of the fields that are filled by 
     // ontology IDs
    var awesomplete_objs = {};
    awesomplete_objs['env_biom'] = new Awesomplete($('#env_biom')[0], { minChars: 2, autoFirst: true });
    awesomplete_objs['env_material'] = new Awesomplete($('#env_material')[0], { minChars: 2, autoFirst: true });
    awesomplete_objs['host_tissue_sampled'] = new Awesomplete($('#host_tissue_sampled')[0], { minChars: 2, autoFirst: true });

    $('.ontology-field').on('awesomplete-selectcomplete', function(e) {
        $(e.target).trigger('input');
    });

    $('.ontology-field').on("keyup", function(evt) {
        var ontology_name = $(this).data('ontologyName');

        if (evt.keyCode != 38 && evt.keyCode != 40 && evt.keyCode != 27) {
            $.ajax({
                url: '/term/' + ontology_name + '/' + this.value,
                type: 'GET',
                dataType: 'json',
                context: this
            })
            .success(function(data) {
                var list = [];
                data.results.forEach(function(record) {
                    list.push({label: record.envo_id + " - " + record.name, value: record.envo_id})
                });

                awesomplete_objs[this.id].list = list;
            })
        }
     });

 });