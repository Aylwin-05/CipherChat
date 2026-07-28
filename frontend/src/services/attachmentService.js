import api from "../api/api";

const attachmentService = {

    // ======================================================
    // Upload Attachment
    // ======================================================

    async upload(
        messageId,
        file,
    ) {

        const formData = new FormData();

        formData.append(
            "file",
            file,
        );

        const response =
            await api.post(

                `/attachments/upload/${messageId}`,

                formData,

                {
                    headers: {
                        "Content-Type":
                            "multipart/form-data",
                    },
                }

            );

        return response.data;

    },

    // ======================================================
    // Download Attachment as Blob URL
    // (JWT automatically included by Axios)
    // ======================================================

    async getImage(
        attachmentId,
    ) {

        const response =
            await api.get(

                `/attachments/${attachmentId}`,

                {
                    responseType: "blob",
                }

            );

        return URL.createObjectURL(
            response.data
        );

    },

};

export default attachmentService;